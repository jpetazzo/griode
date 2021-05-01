use std::fs;
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
// use ws::{listen, CloseCode, Handler, Message, Request, Response,
// 	 Result, ErrorKind, Error, Sender};

// Message formats for ws Server and Client Message
mod shared;

// ---------------------------------------------
// Websocket server code starts
#[derive(Copy, Clone, Debug)]
struct PedalState {

    // `state` is to be set by a pedal.  The pedal available has three
    // pedals, that operate via USB port and look like a keyboard with
    // three keys: 'a', 'b', 'c'.  Changnig `state` will change the
    // LV2 effects loaded into the signal path.
    state:char
}

/// `ServerState` is used by the Server to do its (non-ws) jobs.  It
/// needs to be accessible to the `Handler` instances so they can
/// initialise clients and respond to the client requests.
/// `ServerState` stores the available instruments in a Hash String =>
/// String of names to file paths, and the current instrument as
/// String
#[derive(Clone, Debug)]
struct ServerState {

    // Each instrument is a file in the directory "songs" (FIXME: The
    // name "songs" is terrible).  This is the name of the selected
    // instrument
    selected_instrument: String,

    // Map a instrument name to the path for the file that describes
    // it.  When `control` is used this is the file name passed as
    // argument.  Stored as String not PathBuf because it is not
    // opened in Rust but passed to `control`
    instruments:HashMap<String, String>,
}

impl ServerState {

    fn new() -> Self {
	load_instruments()
    }  
}

struct MyFactoryServer{
    
    // A transmitter for each `Handle` so changes in state can be
    // propagated to the `MyHandlerServer` objects, and thus to the
    // clients
    txs:Arc<Mutex<Vec<mpsc::Sender<PedalState>>>>,

    // The state of the server.  It is shared state, shared with the
    // `MyHandlerServer` objects.  They can change it
    server_state:Arc<Mutex<ServerState>>,

}

struct MyHandlerServer{

    // For communicating with clients
    out:ws::Sender,

    // Local copy of state
    server_state:Arc<Mutex<ServerState>>,

}

impl MyHandlerServer {

    /// The information clients need to bootstrap.
    fn init_for_client(&mut self) -> String {
	let server_state =
	    self.server_state.lock().unwrap();
	let mut ret = format!("{}\n", server_state.selected_instrument);
	for (_, x) in server_state.instruments.iter() {
	    ret = format!("{} {}", ret, x);
	}
	ret += "\n"	;
	ret
    }

    /// `MyHandlerServer` is constructed with three arguments: (1) The
    /// communication channel with clients (2) The channel to get
    /// messages from the factory that created this (3) Shared state.
    /// Shared with all other `MyHandlerServer` objects and the
    /// `MyFactoryServer` object that runs the show
    fn new(
	// Talk to clients
	out:ws::Sender,

	// Get messages from server to send to clients
	rx:mpsc::Receiver<PedalState>,

	// Read and adjust the servers state
    	server_state:Arc<Mutex<ServerState>>,
	
    ) -> Self {
	let mut ret = Self {
	    out:out,
	    server_state:server_state,
	};

	// `run` spawns a thread and runs in background broadcasting
	// changes in state to clients
	ret.run(rx);
	ret
    }

    /// `run` spawns a thread to listen for pedal state changes from
    /// `MyFactoryServer`.  Then pass it on to the clients so they can
    /// update their displays
    fn run(&mut self, rx:mpsc::Receiver<PedalState>){
	// Listem for state updates
	
	println!("MyHandlerServer::run");
	let out_t = self.out.clone();
    	thread::spawn(move || {
    	    loop {
    		let state = match rx.recv() {
		    
		    // Got sent new state information to propagate
    		    Ok(s) => s,

    		    Err(err) => {
    			println!("MyHandlerServer: {:?}", err);
    			break;
    		    }
    		};

    		println!("MyHandlerServer: Got state: {}", state.state);

		// This is the message for the client
		let content = format!("PEDALSTATE {}", state.state);

		let message = shared::ServerMessage {
		    id:out_t.token().into(),
		    text:content,
		};
		
		match send_message(message, &out_t) {
		    Ok(_) => (),
		    Err(err) => panic!("{}",err),
		};
    	    }
	});
    }
}

impl MyFactoryServer {

    fn new() -> Self {
	let ret = Self {
	    txs:Arc::new(Mutex::new(Vec::new())),
	    server_state:Arc::new(Mutex::new(ServerState::new())),
	};
	ret
    }

    /// Spaw a thread to listen for pedal changes on the rx.  When one
    /// is received send it to all the clients so they can update
    /// their displays
    fn run(&mut self, rx:mpsc::Receiver<PedalState>) -> 
	Option<thread::JoinHandle<()>> {
	    println!("MyFactoryServer::run");

	    // Copy of the transmiters to send data to each Handler	    
	    let arc_txs = self.txs.clone();

	    Some(thread::spawn(move || {
		loop {
		    let state = match rx.recv() {
			Ok(s) => s,
			Err(err) => {
			    println!("Sender has hung up: {}", err);
			    break;
			}
		    };
		    println!("MyFactoryServer: Got state: {}",
			     &state.state);

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

    /// What is this doing?  Why?
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

    /// Handle messages recieved in the websocket (in this case, only
    /// on `/ws`)
    fn on_message(&mut self, msg: ws::Message) -> ws::Result<()> {
        let client_id: usize = self.out.token().into();

	// Only process text messages
        if !msg.is_text() {

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

		// The first word of the message (might be) is a command
		let cmds:Vec<&str> = m.text.split_whitespace().collect();

		let response =
		    match cmds[0] {

			// INIT from client is asking for the
			// information it needs to initialise its
			// state.
		    	"INIT" => {

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

			// INSTR is when a user has selected a
			// instrument.  The thing called "PedalState"
			// here is a modification to a instrument made
			// by a pedal on the server.  True story.
			"INSTR" => {
			    // INSTR <instrument name>
			    // User has selected a instrument
			    
			    if cmds.len() > 1 {
				let instrument_name = cmds[1];
				let mut server_state =
				    self.server_state.lock().unwrap();

				info!(
				    "Calling set_instrument({:?})",
				    server_state.
					instruments.get(instrument_name)
					.unwrap()
				);
				set_instrument(
				    server_state
				    // self.server_state.lock().unwrap()
					.instruments.get(instrument_name).
					unwrap()
				);
				server_state.selected_instrument =
				    instrument_name.to_string();
				    
				info!("Returned from set_instrument");
			    }
	    		    shared::ServerMessage{
				id: client_id,
				text: self.server_state.lock().unwrap().
				    selected_instrument.clone()
			    }
			},
			
			// What is this?  Just a echo?
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

fn set_instrument(file_path:&str) {


    info!("set_instrument: file_path {}", file_path);

    let exec_name = format!(
	"{}/control",
	// Why the parent of the current directory?  FIXME This is
	// obscure
	env::current_dir().unwrap()
	    .parent().unwrap()
	    .to_str().unwrap()
    );    

    let cmd = format!("{} {}", exec_name, file_path);
    let mut child = Command::new(exec_name.as_str())
	.arg(file_path)
	.spawn()
	.expect("Failed");
    let ecode = child.wait()
                 .expect("failed to wait on child");
    let res = ecode.success();
    info!("set_instrument: res: {}", res);
    assert!(res);
    info!("set_instrument: {}", cmd);
}

fn send_message(server_msg: shared::ServerMessage,
		out: &ws::Sender) -> ws::Result<()>{
    let server_msg : ws::Message = serde_json::to_string(&server_msg)
	.unwrap()
	.into();
    out.broadcast(server_msg)
}    

fn load_instruments() -> ServerState {

    // Build the list of song files (TODO "song" is a bad name!) and
    // select one to be current. That defines a `ServerState`.

    // The "songs" are configuration files, all in the same directory.
    // In that directory there is a file "LIST" that has the "songs"
    // that will be presented to the user.

    // First find the directory:
    let dir = match env::var("INSTRUMENT_DIRECTORY"){
	Ok(d) => d,
	Err(_) => {
	    // Environment variable not set.  Try to find it relative
	    // to the current directory
	    
	    
	    // Find the direcory with the instrument data in it.
	    let current_dir = env::current_dir().unwrap();
	    let dir = current_dir.parent().unwrap();
	    dir.to_str().unwrap().to_string() + "/songs"
	},
    };

    // Check `dir` exists and names a directory
    assert!(fs::metadata(dir.as_str()).unwrap().file_type().is_dir());

    // Get the list of instruments that are used. There can be more
    // instruments in the directpry than are used.
    let list_name = format!("{}/LIST", &dir);
    
    // Check `dir` exists and does not name a directory
    assert!(!fs::metadata(list_name.as_str()).unwrap().file_type().is_dir());

    info!("list_name: {}", list_name);

    let mut list_d = String::new();

    File::open(list_name.as_str()).unwrap()
	.read_to_string(&mut list_d).unwrap();

    // The names of the instruments to use
    let  instrument_names:Vec<&str> =
	list_d.as_str().lines().filter(

	    |x| x
		// This is opaque!  It skips blank lines and lines
		// where first non-whitespace character is '#'

		// Split line into whitspace seperated words
		.split_whitespace()
		
		// Choose the next word.  If no words return "#"
		.next().unwrap_or("#")
		
		.bytes().next() // Get first byte

		.unwrap() != b'#' // If it is not '#' then line accepted

	).collect();
    
    if instrument_names.len() == 0 {
	panic!("No instruments in list");
    }
    
    info!("Instruments: {}",
	  instrument_names.iter().fold(String::new(),
				 |a, b| format!("{} {}", a, b)));

    let dir = PathBuf::from(dir.as_str());
    if !dir.is_dir() {
	panic!("{} is not a directory!", dir.to_str().unwrap());
    }

    
    let selected_instrument = String::from(instrument_names[0]);
    let mut instruments = HashMap::new();

    for entry in dir.read_dir().expect("read_dir call failed") {
	if let Ok(entry) = entry {
	    // entry is std::fs::DirEntry
	    let p = entry.path();

	    // Files with no extension are descriptions of settings
	    // for the instrument so find them
	    if p.as_path().is_file() &&
		p.as_path().extension().is_none() {

		    // Just the name, extraced from the path
		    let instrument_name =
			p.file_name().unwrap()
			.to_str().unwrap()
			.to_string();

		    // If the instrument name is in the list of
		    // instruments to present to the user then store
		    // it in the vector
		    if instrument_names.contains(&instrument_name.as_ref()) {
			instruments.insert(instrument_name.clone(),
				    p.to_str().unwrap().to_string());
		    }else{
		    }			    
		}
	}	
    }
    ServerState {
	selected_instrument:selected_instrument,
	instruments:instruments,
    }
}

fn main() -> std::io::Result<()>{
    // Listen on an address and call the closure for each connection
    SimpleLogger::new().init().unwrap();
    info!("Starting server");

    // Create channel to communicate with the server.  
    let (tx, rx) = mpsc::channel();

    let mut my_factory = MyFactoryServer::new();
    let server_handle = my_factory.run(rx);
    let wss = ws::WebSocket::new(my_factory).unwrap();
    

    let s_thread = thread::spawn(move || {
	wss.listen("0.0.0.0:9000").unwrap()
    });
    
    thread::spawn(move || {
	// Simulate a pedal 
	for _ in 0..10 {
	    let onhundred_millis = time::Duration::from_millis(100);
	    thread::sleep(onhundred_millis);
	    tx.send(PedalState{state:'a'}).unwrap();
	}
    });
    server_handle.unwrap().join().unwrap();
    s_thread.join().unwrap();
    Ok(())
}
