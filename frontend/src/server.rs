use ws::{listen, CloseCode, Handler, Message, Request, Response,
	 Result, ErrorKind, Error, Sender};
use std::fs::File;
use std::io::prelude::*;
use std::process::Command;
// https://docs.rs/ws/


use std::{env,  path::PathBuf, collections::HashMap};
//use serde_json::Result;

mod shared;



struct Server {
    out: Sender,
    settings: HashMap<String, PathBuf>,
    current_instrument: String,
}

impl Server {
    fn init_for_client(&mut self) -> String {

	// Find the direcory with the instrument data in it.
	let current_dir = env::current_dir().unwrap();
	let dir = current_dir.parent().unwrap();
	let dir_name = dir.to_str().unwrap().to_string() + "/songs";
	let list_name = dir.to_str().unwrap().to_string() + "/songs/LIST";

	let mut list_d = String::new();
	println!("list_name: {}", list_name);
	File::open(list_name.as_str()).unwrap().read_to_string(&mut list_d).unwrap();
	let  song_names:Vec<&str> =
	    list_d.as_str().lines().filter(|x| x
					   .split_whitespace()
					   .next().unwrap_or("#")
					   .bytes().next()
					   .unwrap() != b'#').collect();
	
	println!("Songs: {}", song_names.iter().fold(String::new(), |a, b| format!("{} {}", a, b)));

	if song_names.len() == 0 {
	    panic!("No songs in list");
	}
	
	let dir = PathBuf::from(dir_name.as_str());
	if !dir.is_dir() {
	    panic!("{} is not a directory!", dir.to_str().unwrap());
	}
	self.settings = HashMap::new();

	

	// Todo Remember this between invocations
	self.current_instrument = song_names[0].to_string();


	for entry in dir.read_dir().expect("read_dir call failed") {
	    if let Ok(entry) = entry {
		// entry is std::fs::DirEntry
		let p = entry.path();
		if p.as_path().is_file() &&
		    p.as_path().extension().is_none() {
			// Files with no extension are descriptions of
			// settings for the instrument
//			let song_name = PathBuf::from(p.into_os_string().to_str().unwrap());
			let song_name = p.file_name().unwrap().to_str().unwrap().to_string();
			print!("Song name: {} ", song_name);
			if song_names.contains(&song_name.as_ref()) {
			    println!("In");
			    self.settings.insert(song_name.clone(),
						 PathBuf::from(song_name));
			}else{
			    println!("Out");
			}			    
		    }
	    }	
	}

	self.settings.iter().fold(
	    String::new(), |a, b| a + " " + b.0.as_str()
	)
    }
}    

fn get_dir() -> String {
    let current_dir = env::current_dir().unwrap();
    let dir = current_dir.parent().unwrap();
    dir.to_str().unwrap().to_string() + "/songs"
}

fn set_instrument(p:PathBuf) -> String {

    let dir_name = get_dir();
    let instrument = p.as_os_str().to_str().unwrap().to_string();
    let file_path = format!("{}/{}",
			    dir_name,
			    &instrument);

    println!("set_instrument: file_path {}", file_path);
    let exec_name = format!("{}/control", env::current_dir().unwrap()
	.parent().unwrap().to_str().unwrap());    
    let cmd = format!("{} {}", exec_name, file_path);
    let mut child = Command::new(exec_name.as_str())
	.arg(file_path.as_str())
	.spawn()
	.expect("Failed");
    let ecode = child.wait()
                 .expect("failed to wait on child");
    let res = ecode.success();
    println!("set_instrument: res: {}", res);
    assert!(res);
    println!("set_instrument: {}", cmd);
    instrument
}
impl Handler for Server {
    fn on_request(&mut self, req: &Request) -> Result<Response> {
        match req.resource() {
            "/ws" => Response::from_request(req),
            _ => Ok(Response::new(
                200,
                "OK",
                b"Websocket server is running".to_vec(),
            )),
        }
    }

    // Handle messages recieved in the websocket (in this case, only on `/ws`).
    fn on_message(&mut self, msg: Message) -> Result<()> {
        let client_id: usize = self.out.token().into();
        if !msg.is_text() {
	    Err(Error::new(
		ErrorKind::Internal,
		"Unknown message type"))
	}else{
	    // `msg` is type: `ws::Message::Text(String)` The
	    // contained string is JSON shared::ServerMessage
	    if let Message::Text(client_msg)  = msg {
		println!("client_msg: {}", client_msg);
		let m:shared::ClientMessage =
		    serde_json::from_str(client_msg.as_str()).unwrap();
		let cmds:Vec<&str> = m.text.split_whitespace().collect();
		let response =
		    match cmds[0] {
		    	"INIT" => {
			    // Client is asking for the data it needs to set up
			    let return_msg = format!("INIT {}", self.init_for_client());
		    	    println!("Got INIT\nSEND: {}", return_msg);			    
	    		    shared::ServerMessage{id: client_id, text: return_msg }
		    	},
			"INSTR" => {
			    // User has selected a instrument
			    if cmds.len() > 1 {
				println!(
				    "Calling set_instrument({:?})",
				    self.settings.get(cmds[1])
					.unwrap()
					.to_path_buf()
				);
				self.current_instrument = set_instrument(self.settings.get(cmds[1]).unwrap().to_path_buf());
				println!("Returned from set_instrument");
			    }
	    		    shared::ServerMessage{id: client_id,
						  text: self.current_instrument.clone()}
			},
		    	key => shared::ServerMessage{
			    id: client_id,
			    text: key.to_string()
			}
		    };
		// Broadcast to all connections.
		
		println!("Send response: '{:?}'", response.text);
		send_message(response, &self.out)
	    }else{
		panic!("No!")
	    }
	}
    }

    fn on_close(&mut self, code: CloseCode, reason: &str) {
        let client_id: usize = self.out.token().into();
        let code_number: u16 = code.into();
        println!(
            "WebSocket closing - client: {}, code: {} {:?}, reason: {}",
            client_id, code_number, code, reason
        );
    }

}

fn send_message(server_msg: shared::ServerMessage,
		out: &Sender) -> Result<()>{
    let server_msg : Message = serde_json::to_string(&server_msg)
	.unwrap()
	.into();
    out.broadcast(server_msg)
}    

// fn handle_text_message(client_id: usize, msg: Message) -> Message {
//     let client_msg: shared::ClientMessage =
//         serde_json::from_str(&msg.into_text().unwrap()).unwrap();

//     println!( "> text: '{}'", client_msg.text );

//     let server_msg: Message = serde_json::to_string(&shared::ServerMessage {
//         id: client_id,
//         text: client_msg.text,
//     })
//     .unwrap()
//     .into();

//     server_msg
// }


fn main() {
    // Listen on an address and call the closure for each connection
    println!("Starting server");
    listen("0.0.0.0:9000", |out| Server { out:out,
					  current_instrument: String::new(),
					  settings:HashMap::new() }).unwrap()
}
