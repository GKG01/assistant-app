use serde::{Deserialize, Serialize};
use std::{
    io::{BufRead, BufReader, Write},
    path::Path,
    process::{Child, ChildStdin, Command, Stdio},
    sync::mpsc,
    time::Duration,
};

#[derive(Clone, Serialize)]
pub struct Session {
    pub token: String,
}

pub struct Backend {
    child: Child,
    _input: ChildStdin,
    session: Session,
}

#[derive(Deserialize)]
struct Ready {
    status: String,
}

impl Backend {
    pub fn start(directory: &Path) -> Result<Self, String> {
        let python = if cfg!(windows) {
            directory.join(".venv/Scripts/python.exe")
        } else {
            directory.join(".venv/bin/python")
        };
        if !python.is_file() || !directory.join("managed.py").is_file() {
            return Err("Nova backend is missing. Create backend/.venv and install requirements.txt, then restart Nova.".into());
        }
        let mut bytes = [0u8; 32];
        getrandom::fill(&mut bytes).map_err(|_| "Could not generate a secure desktop session.")?;
        let token: String = bytes.iter().map(|byte| format!("{byte:02x}")).collect();
        let mut command = Command::new(python);
        command
            .args(["-u", "managed.py"])
            .current_dir(directory)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000); // CREATE_NO_WINDOW
        }
        let mut child = command
            .spawn()
            .map_err(|_| "Could not start Nova's Python backend.")?;
        let input = child
            .stdin
            .take()
            .ok_or("Backend input pipe is unavailable.")?;
        let output = child
            .stdout
            .take()
            .ok_or("Backend output pipe is unavailable.")?;
        let mut backend = Self {
            child,
            _input: input,
            session: Session { token },
        };
        // Write only to the child's inherited pipe, never argv, env, disk or logs.
        writeln!(
            backend._input,
            "{{\"token\":\"{}\"}}",
            backend.session.token
        )
        .map_err(|_| "Could not initialize the backend session.")?;
        let (sender, receiver) = mpsc::channel();
        std::thread::spawn(move || {
            let mut line = String::new();
            let result = BufReader::new(output).read_line(&mut line);
            let ready = result.is_ok()
                && serde_json::from_str::<Ready>(&line)
                    .map(|message| message.status == "ready")
                    .unwrap_or(false);
            let _ = sender.send(ready);
        });
        if !receiver
            .recv_timeout(Duration::from_secs(20))
            .unwrap_or(false)
        {
            return Err("Nova backend could not start. Stop any backend using port 8000, check .env and Python dependencies, then restart Nova.".into());
        }
        backend.session()?;
        Ok(backend)
    }

    pub fn session(&mut self) -> Result<Session, String> {
        match self.child.try_wait() {
            Ok(None) => Ok(self.session.clone()),
            _ => Err("Nova backend stopped. Close and restart the desktop app.".into()),
        }
    }
}

impl Drop for Backend {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_backend_does_not_fall_back_to_path_python() {
        assert!(Backend::start(Path::new("/nonexistent/nova/backend")).is_err());
    }

    #[test]
    fn handshake_requires_ready_status() {
        assert_eq!(
            serde_json::from_str::<Ready>(r#"{"status":"ready"}"#)
                .unwrap()
                .status,
            "ready"
        );
        assert!(serde_json::from_str::<Ready>("not json").is_err());
    }

    #[test]
    #[cfg(windows)]
    fn managed_backend_lifecycle_and_authentication() {
        use std::io::Read;
        use std::net::TcpStream;

        fn request(token: Option<&str>) -> String {
            let mut stream = TcpStream::connect("127.0.0.1:8000").unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            let auth = token
                .map(|value| format!("Authorization: Bearer {value}\r\n"))
                .unwrap_or_default();
            write!(stream, "GET /files/search HTTP/1.1\r\nHost: 127.0.0.1:8000\r\nX-Nova-Request: 1\r\n{auth}Connection: close\r\n\r\n").unwrap();
            let mut response = String::new();
            stream.read_to_string(&mut response).unwrap();
            response
        }

        // This test owns the only live backend in this test binary. Never touch user data.
        let temporary =
            std::env::temp_dir().join(format!("nova-session-test-{}", std::process::id()));
        std::fs::create_dir_all(&temporary).unwrap();
        let old_database = std::env::var_os("NOVA_DATABASE_PATH");
        let old_roots = std::env::var_os("NOVA_ALLOWED_DIRECTORIES");
        std::env::set_var("NOVA_DATABASE_PATH", temporary.join("index.db"));
        std::env::set_var("NOVA_ALLOWED_DIRECTORIES", "[]");
        let directory = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../backend");
        let mut first =
            Backend::start(&directory).expect("Install backend dependencies and free port 8000");
        let first_token = first.session().unwrap().token;
        assert!(request(None).starts_with("HTTP/1.1 401"));
        assert!(request(Some(&first_token)).starts_with("HTTP/1.1 200"));
        assert!(
            Backend::start(&directory).is_err(),
            "Never attach to an existing listener"
        );
        assert!(request(Some(&first_token)).starts_with("HTTP/1.1 200"));
        drop(first);
        assert!(TcpStream::connect("127.0.0.1:8000").is_err());
        let mut second = Backend::start(&directory).unwrap();
        let second_token = second.session().unwrap().token;
        assert!(
            first_token != second_token,
            "Each launch needs a new credential"
        );
        assert!(request(Some(&first_token)).starts_with("HTTP/1.1 401"));
        assert!(request(Some(&second_token)).starts_with("HTTP/1.1 200"));
        second.child.kill().unwrap();
        second.child.wait().unwrap();
        assert!(second.session().is_err());
        drop(second);
        for (name, old) in [
            ("NOVA_DATABASE_PATH", old_database),
            ("NOVA_ALLOWED_DIRECTORIES", old_roots),
        ] {
            match old {
                Some(value) => std::env::set_var(name, value),
                None => std::env::remove_var(name),
            }
        }
    }
}
