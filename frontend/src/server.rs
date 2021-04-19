// use ws::{listen, CloseCode, Handler, Message, Request, Response,
// 	 Result, ErrorKind, Error, Sender};

// use std::sync::mpsc::{Sender, Receiver};
//use serde_json::Result;
use std::fs::File;
use std::io::prelude::*;
use std::process::Command;
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time;
use std::{env,  path::PathBuf, collections::HashMap};

use log::{info}; //, trace, warn};
use simple_logger::SimpleLogger;

// https://docs.rs/ws/
use ws;

mod shared;

// ---------------------------------------------
// Websocket server code starts
#[derive(Copy, Clone, Debug)]
struct State {
    state:char
}

/// `ServerState` is used by the Server to do its (non-ws) jobs.  It
/// needs to be accessible to the `Handler` instances so they can
/// initialise clients and respond to the client requests.
#[derive(Clone, Debug)]
struct ServerState {
    things:Vec<String>,
    thing:String,
}

struct MyFactoryServer{
    
    // A transmitter for each `Handle`
    txs:Arc<Mutex<Vec<mpsc::Sender<State>>>>,
    
    server_state:Arc<Mutex<ServerState>>,

}

struct MyHandlerServer{
    out:ws::Sender,
    settings: HashMap<String, PathBuf>,

    server_state:Arc<Mutex<ServerState>>,

}

impl ws::Factory for MyFactoryServer {
    type Handler = MyHandlerServer;
    fn connection_made(&mut self, out: ws::Sender) -> Self::Handler{
	let (tx, rx) = mpsc::channel();
	self.txs.lock().unwrap().push(tx);
	println!("Server handing out a Handler");
        MyHandlerServer::new(out, rx, self.server_state.clone())
    }
}

impl ws::Handler for MyHandlerServer {
    fn on_request(&mut self, req: &ws::Request) -> ws::Result<ws::Response> {
        match req.resource() {
            "/ws" => ws::Response::from_request(req),
            _ => Ok(ws::Response::new(
                200,
                "OK",
                b"Websocket server is running".to_vec(),
            )),
        }
    }

    // Handle messages recieved in the websocket (in this case, only on `/ws`).
    fn on_message(&mut self, msg: ws::Message) -> ws::Result<()> {
        let client_id: usize = self.out.token().into();

        if !msg.is_text() {
	    // There are two types of websocket in ws.rs: Text,
	    // Binary.  Only Text is handled See
	    // https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/binaryType
	    // for details of binary types
	    Err(ws::Error::new(
		ws::ErrorKind::Internal,
		"Unknown message type"))
	}else{
	    // `msg` is type: `ws::Message::Text(String)` The
	    // contained string is JSON shared::ServerMessage
	    if let ws::Message::Text(client_msg)  =  msg {
		info!("client_msg: {}", client_msg);
		let m:shared::ClientMessage =
		    serde_json::from_str(client_msg.as_str()).unwrap();
		let cmds:Vec<&str> = m.text.split_whitespace().collect();
		let response =
		    match cmds[0] {

		    	"INIT" => {
			    // Client is asking for the data it needs to set up

			    let return_msg = format!(
				"INIT {}",
				self.init_for_client()
			    );
		    	    info!("Got INIT\nSEND: {}", return_msg);			    
	    		    shared::ServerMessage{
				id: client_id,
				text: return_msg
			    }
		    	},

			"INSTR" => {
			    // User has selected a instrument
			    if cmds.len() > 1 {
				info!(
				    "Calling set_instrument({:?})",
				    self.settings.get(cmds[1])
					.unwrap()
					.to_path_buf()
				);
				self.server_state.lock().unwrap().thing =
				    set_instrument(
					self.settings.get(cmds[1]).unwrap().
					    to_path_buf());
				info!("Returned from set_instrument");
			    }
	    		    shared::ServerMessage{
				id: client_id,
				text: self.server_state.lock().unwrap().
				    thing.clone()
			    }
			},
		    	key => shared::ServerMessage{
			    id: client_id,
			    text: key.to_string()
			}
		    };
		// Broadcast to all connections.
		
		info!("Send response: '{:?}'", response.text);
		send_message(response, &self.out)
	    }else{
		panic!("No!")
	    }
	}
    }

    fn on_close(&mut self, code: ws::CloseCode, reason: &str) {
        let client_id: usize = self.out.token().into();
        let code_number: u16 = code.into();
        info!(
            "WebSocket closing - client: {}, code: {} {:?}, reason: {}",
            client_id, code_number, code, reason
        );
    }
}

impl MyFactoryServer {
    // fn new(rx:mpsc::Receiver<State>) -> Self {
    fn new() -> Self {
	let ret = Self {
	    txs:Arc::new(Mutex::new(Vec::new())),
	    server_state:Arc::new(Mutex::new(ServerState{
		things:Vec::new(),
		thing:String::new(),
	    })),
	};
	ret
    }

    fn run(&mut self, rx:mpsc::Receiver<State>) -> 
	Option<thread::JoinHandle<()>> {
	    println!("MyFactoryServer::run");
	    let arc_txs = self.txs.clone();
	    Some(thread::spawn(move || {
		loop {
		    let state = match rx.recv() {
			Ok(s) => s,
			Err(err) => {
			    println!("rx error: {:?}", err);
			    break;
			}
		    };
		    println!("MyFactoryServer: Got state: {}", &state.state);

		    for tx in &*arc_txs.lock().unwrap() {
		        match tx.send(state) {
			    Ok(x) => println!("FactoryServer sent: {:?}", x),
			    Err(e) => println!("FactoryServer err: {:?}", e),
			};
		    }
		};
	    }))
	}
}


impl MyHandlerServer {
    fn init_for_client(&mut self) -> String {

	// Find the direcory with the instrument data in it.
	let current_dir = env::current_dir().unwrap();
	let dir = current_dir.parent().unwrap();
	let dir_name = dir.to_str().unwrap().to_string() + "/songs";
	let list_name = dir.to_str().unwrap().to_string() + "/songs/LIST";

	let mut list_d = String::new();
	info!("list_name: {}", list_name);

	File::open(list_name.as_str()).unwrap()
	    .read_to_string(&mut list_d).unwrap();

	let  song_names:Vec<&str> =
	    list_d.as_str().lines().filter(|x| x
					   .split_whitespace()
					   .next().unwrap_or("#")
					   .bytes().next()
					   .unwrap() != b'#').collect();
	
	info!("Songs: {}",
	      song_names.iter().fold(String::new(),
				     |a, b| format!("{} {}", a, b)));

	if song_names.len() == 0 {
	    panic!("No songs in list");
	}
	
	let dir = PathBuf::from(dir_name.as_str());
	if !dir.is_dir() {
	    panic!("{} is not a directory!", dir.to_str().unwrap());
	}
	self.settings = HashMap::new();

	// Todo Remember this between invocations
	self.server_state.lock().unwrap().thing = song_names[0].to_string();

	for entry in dir.read_dir().expect("read_dir call failed") {
	    if let Ok(entry) = entry {
		// entry is std::fs::DirEntry
		let p = entry.path();
		if p.as_path().is_file() &&
		    p.as_path().extension().is_none() {
			// Files with no extension are descriptions of
			// settings for the instrument
			let song_name =
			    p.file_name().unwrap()
			    .to_str().unwrap()
			    .to_string();
			info!("Song name: {} ", song_name);
			if song_names.contains(&song_name.as_ref()) {
			    info!("In");
			    self.settings.insert(song_name.clone(),
						 PathBuf::from(song_name));
			}else{
			    info!("Out");
			}			    
		    }
	    }	
	}

	self.settings.iter().fold(
	    String::new(), |a, b| a + " " + b.0.as_str()
	)
    }
    fn new(
	out:ws::Sender,
	rx:mpsc::Receiver<State>,
    	server_state:Arc<Mutex<ServerState>>,
    ) -> Self {
	let mut ret = Self {
	    out:out,
	    server_state:server_state,
	    settings:HashMap::new(),
	};
	ret.run(rx);
	ret
    }
    fn run(&mut self, rx:mpsc::Receiver<State>){
	println!("MyHandlerServer::run");
	let out_t = self.out.clone();
    	thread::spawn(move || {
    	    loop {
    		let state = match rx.recv() {
    		    Ok(s) => s,
    		    Err(err) => {
    			println!("MyHandlerServer: {:?}", err);
    			break;
    		    }
    		};
    		println!("MyHandlerServer: Got state: {}", state.state);

		match out_t.send(format!("Server sending state: {:?}", state)
				 .as_str()) {
		    Ok(x) =>
			println!("MyHandlerServer::run Sent {:?} result: {:?}",
				 state, x),
		    Err(x) => panic!("{}", x),
		};
    	    };
    	});
    }	
}

// Websocket server code ends
// ---------------------------------------------


// struct Instruments {
//     // Instruments are defined by a list of strings.  This i sa short
//     // list.  These are instruments for the menu to be used in a live
//     // setting.  As of writting (20210402) the instruments to offer
//     // are defined in a directory relative to the current directory
//     // "songs/LIST".  (That name is not a good one and should change)
//     instruments: Vec<String>
// }
// impl Instruments {
//     fn new() ->  Self {
// 	Instruments {
// 	    instruments:Vec::new(),
// 	}
//     }
// }

// struct Server {
//     out: ws::Sender,
//     settings: HashMap<String, PathBuf>,
//     current_instrument: String,
//     instruments:Instruments,
//     signal: Option<Arc<dyn Fn(char) -> ()>>,
// }

// impl Server {

//     fn new(out:ws::Sender,) -> Self {

// 	Server{
// 	    out:out,
// 	    current_instrument: String::new(),
// 	    settings:HashMap::new(),
// 	    instruments:Instruments::new(),
// 	    signal:None,
// 	}
//     }

//     fn init_for_client(&mut self) -> String {

// 	// Find the direcory with the instrument data in it.
// 	let current_dir = env::current_dir().unwrap();
// 	let dir = current_dir.parent().unwrap();
// 	let dir_name = dir.to_str().unwrap().to_string() + "/songs";
// 	let list_name = dir.to_str().unwrap().to_string() + "/songs/LIST";

// 	let mut list_d = String::new();
// 	info!("list_name: {}", list_name);

// 	File::open(list_name.as_str()).unwrap()
// 	    .read_to_string(&mut list_d).unwrap();

// 	let  song_names:Vec<&str> =
// 	    list_d.as_str().lines().filter(|x| x
// 					   .split_whitespace()
// 					   .next().unwrap_or("#")
// 					   .bytes().next()
// 					   .unwrap() != b'#').collect();
	
// 	info!("Songs: {}",
// 	      song_names.iter().fold(String::new(),
// 				     |a, b| format!("{} {}", a, b)));

// 	if song_names.len() == 0 {
// 	    panic!("No songs in list");
// 	}
	
// 	let dir = PathBuf::from(dir_name.as_str());
// 	if !dir.is_dir() {
// 	    panic!("{} is not a directory!", dir.to_str().unwrap());
// 	}
// 	self.settings = HashMap::new();

// 	// Todo Remember this between invocations
// 	self.current_instrument = song_names[0].to_string();


// 	for entry in dir.read_dir().expect("read_dir call failed") {
// 	    if let Ok(entry) = entry {
// 		// entry is std::fs::DirEntry
// 		let p = entry.path();
// 		if p.as_path().is_file() &&
// 		    p.as_path().extension().is_none() {
// 			// Files with no extension are descriptions of
// 			// settings for the instrument
// 			let song_name =
// 			    p.file_name().unwrap()
// 			    .to_str().unwrap()
// 			    .to_string();
// 			info!("Song name: {} ", song_name);
// 			if song_names.contains(&song_name.as_ref()) {
// 			    info!("In");
// 			    self.settings.insert(song_name.clone(),
// 						 PathBuf::from(song_name));
// 			}else{
// 			    info!("Out");
// 			}			    
// 		    }
// 	    }	
// 	}

// 	self.settings.iter().fold(
// 	    String::new(), |a, b| a + " " + b.0.as_str()
// 	)
//     }

//     fn broadcast(&self, c:char) {
// 	let client_id: usize = self.out.token().into();
	
// 	send_message(shared::ServerMessage {
// 	    id: client_id,
// 	    text: format!("DETAIL {}", c),
// 	}, &self.out);
		     
//     }
    
// }    

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

    info!("set_instrument: file_path {}", file_path);

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
    info!("set_instrument: res: {}", res);
    assert!(res);
    info!("set_instrument: {}", cmd);
    instrument
}

// impl ws::Handler for Server {

//     fn on_request(&mut self, req: &ws::Request) -> ws::Result<ws::Response> {
//         match req.resource() {
//             "/ws" => ws::Response::from_request(req),
//             _ => Ok(ws::Response::new(
//                 200,
//                 "OK",
//                 b"Websocket server is running".to_vec(),
//             )),
//         }
//     }

//     // Handle messages recieved in the websocket (in this case, only on `/ws`).
//     fn on_message(&mut self, msg: ws::Message) -> ws::Result<()> {
//         let client_id: usize = self.out.token().into();

//         if !msg.is_text() {
// 	    // There are two types of websocket in ws.rs: Text,
// 	    // Binary.  Only Text is handled See
// 	    // https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/binaryType
// 	    // for details of binary types
// 	    Err(ws::Error::new(
// 		ws::ErrorKind::Internal,
// 		"Unknown message type"))
// 	}else{
// 	    // `msg` is type: `ws::Message::Text(String)` The
// 	    // contained string is JSON shared::ServerMessage
// 	    if let ws::Message::Text(client_msg)  =  msg {
// 		info!("client_msg: {}", client_msg);
// 		let m:shared::ClientMessage =
// 		    serde_json::from_str(client_msg.as_str()).unwrap();
// 		let cmds:Vec<&str> = m.text.split_whitespace().collect();
// 		let response =
// 		    match cmds[0] {
// 		    	"INIT" => {
// 			    // Client is asking for the data it needs to set up
// 			    let return_msg = format!(
// 				"INIT {}",
// 				self.init_for_client()
// 			    );
// 		    	    info!("Got INIT\nSEND: {}", return_msg);			    
// 	    		    shared::ServerMessage{
// 				id: client_id,
// 				text: return_msg
// 			    }
// 		    	},
// 			"INSTR" => {
// 			    // User has selected a instrument
// 			    if cmds.len() > 1 {
// 				info!(
// 				    "Calling set_instrument({:?})",
// 				    self.settings.get(cmds[1])
// 					.unwrap()
// 					.to_path_buf()
// 				);
// 				self.current_instrument = set_instrument(self.settings.get(cmds[1]).unwrap().to_path_buf());
// 				info!("Returned from set_instrument");
// 			    }
// 	    		    shared::ServerMessage{id: client_id,
// 						  text: self.current_instrument.clone()}
// 			},
// 		    	key => shared::ServerMessage{
// 			    id: client_id,
// 			    text: key.to_string()
// 			}
// 		    };
// 		// Broadcast to all connections.
		
// 		info!("Send response: '{:?}'", response.text);
// 		send_message(response, &self.out)
// 	    }else{
// 		panic!("No!")
// 	    }
// 	}
//     }

//     fn on_close(&mut self, code: ws::CloseCode, reason: &str) {
//         let client_id: usize = self.out.token().into();
//         let code_number: u16 = code.into();
//         info!(
//             "WebSocket closing - client: {}, code: {} {:?}, reason: {}",
//             client_id, code_number, code, reason
//         );
//     }
// }

fn send_message(server_msg: shared::ServerMessage,
		out: &ws::Sender) -> ws::Result<()>{
    let server_msg : ws::Message = serde_json::to_string(&server_msg)
	.unwrap()
	.into();
    out.broadcast(server_msg)
}    


fn main() -> std::io::Result<()>{
    // Listen on an address and call the closure for each connection
    SimpleLogger::new().init().unwrap();
    info!("Starting server");

    // Create channel to communicate with the server.  
    let (tx, rx) = mpsc::channel();

    let mut my_server = MyFactoryServer::new();
    let server_handle = my_server.run(rx);
    let wss = ws::WebSocket::new(my_server).unwrap();
    

    let s_thread = thread::spawn(move || {
	wss.listen("0.0.0.0:9000").unwrap()
    });
    
    thread::spawn(move || {
	for _ in 0..10 {
	    let onhundred_millis = time::Duration::from_millis(100);
	    thread::sleep(onhundred_millis);
	    tx.send(State{state:'a'}).unwrap();
	}
    });
    server_handle.unwrap().join().unwrap();
    s_thread.join().unwrap();
    Ok(())
}
