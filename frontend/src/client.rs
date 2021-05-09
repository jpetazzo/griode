use seed::{prelude::*, *};
use std::rc::Rc;
mod shared;
//use std::time::SystemTime;
use chrono::{Local, DateTime};
const WS_URL: &str = "ws://patchbox.local:9000/ws";

// The selected instrument is either initialising (when it has been
// selected but before it is...)  or ready
#[derive(PartialEq)]
enum SelectedState {
    Initialising,
    Ready,
}

/// When a instrument is selected in the user interface this is
/// initialised with the name of the instrument and
/// `SelectedState::Initialising`.  When the server responds that the
/// instrument is ready the state is changed to
/// `SelectedState::Ready`.
#[derive(PartialEq)]
struct Selected {
    name:String,
    state: SelectedState,
}

pub struct Model {

    // Each instrument is represented by a string
    instruments: Vec<String>,

    // There is zero or one selected instrument.  Store it with its
    // name and state.  If none selected it is None
    selected:Option<Selected>,

    // The server has a pedal attached to it.  It can be in any of a
    // number of states (three with current pedal).  The state of the
    // pedal is expressed by a character.
    pedal_state:char,

    // Count how many messages get sent.  FIXME Why?  
    sent_messages_count: usize,

    // All messages received end up in here.  FIXME Why?
    messages: Vec<String>,

    input_text: String,
    input_binary: String,
    web_socket: WebSocket,
    web_socket_reconnector: Option<StreamHandle>,
}

// A little function that outputs the time string for now
fn my_now() -> String {
    let dt: DateTime<Local> = Local::now();
    return dt.to_rfc3339()
}



pub enum Msg {
    WebSocketOpened,
    TextMessageReceived(shared::ServerMessage),
    BinaryMessageReceived(shared::ServerMessage),
    CloseWebSocket,
    WebSocketClosed(CloseEvent),
    WebSocketFailed,
    ReconnectWebSocket(usize),
    InputTextChanged(String),
    InputBinaryChanged(String),
    SendMessage(shared::ClientMessage),
    SendBinaryMessage(shared::ClientMessage),
}


/// Create a `WebSocket` with handlers: `decode_message` called when a
/// message is received from the server.  The other `open`, `close`,
/// `error` handlers are simple closures returning a `Msg`
fn create_websocket(orders: &impl Orders<Msg>) -> WebSocket {

    // `msg_sender` set to the function that invokes the update
    // function
    let msg_sender = orders.msg_sender();

    WebSocket::builder(WS_URL, orders)
        .on_open(|| Msg::WebSocketOpened)
        .on_message(move |msg| decode_message(msg, msg_sender))
        .on_close(Msg::WebSocketClosed)
        .on_error(|| Msg::WebSocketFailed)
        .build_and_open()
        .unwrap()
}

/// Called with the msg passed and a pointer, `Rc`, to the function
/// called when a message is received.  TODO Grok why, what that
/// function is.  The function is called with
/// `Option<Msg>::BinaryMessageReceived` or
/// `Option<Msg>::TestMessageReceived`.  Why????
fn decode_message(
    message: WebSocketMessage,
    msg_sender: Rc<dyn Fn(Option<Msg>)>
){
    if message.contains_text() {
        let msg = message
            .json::<shared::ServerMessage>()
            .expect("Failed to decode WebSocket text message");

        msg_sender(Some(Msg::TextMessageReceived(msg)));
    } else {
        spawn_local(async move {
            let bytes = message
                .bytes()
                .await
                .expect("WebsocketError on binary data");

            let msg: shared::ServerMessage =
		rmp_serde::from_slice(&bytes).unwrap();
            msg_sender(Some(Msg::BinaryMessageReceived(msg)));
        });
    }
}

/// Called by `view` to generate some HTML code for a instrument.
/// Returns the div for the instrument
fn instrument_div(
    instrument: String,
    pedal_state:char,
    height:f32, // Proportion of page
    selected:&Option<Selected>
) -> Node<Msg> {

    // If this instrument is the selected instrument the class will be
    // "initialising" or "selected" depending on whether the server
    // has confirmed it is ready.  Else it is "unselected"
    let class = match selected {
	None =>  "unselected",
	Some(state) => {
	    if state.name == instrument {
		match state.state {
		    SelectedState::Initialising => "initialising",
		    SelectedState::Ready => "selected",
		}
	    }else{
		"unselected"
	    }
	},
    };
    
    // For CSS height is in percent.  0 < height < 1
    let height_div_percent = (100.0 * height).floor();

    // To send to server on click.  Causes this instrument to be
    // selected
    let message = format!("INSTR {}", &instrument);

    // HTML to return
    div![
	C![class],	
        ev(
	    Ev::Click,
	    {
		// log!(my_now(), my_now(), "Ev::Click Setup", instrument);
		let instrument_clone = instrument.clone();
		// Return the closure to execute if there is a click
		move |_| {
		    log!(my_now(), "Ev::Click ", instrument_clone);
		    Msg::SendMessage(shared::ClientMessage { text: message })
		}
            }
	),

	// The span that contains all UI for a instrument
	span![

	    // The class of the span
	    C!["instrument_name"],
	    
	    style![
		// The whole page is 10em: ?? Is that a measurement of
		// a particular piece of hardware, a assumtion, or a
		// definition?
		St::FontSize =>
		    format!("{}em", (10.0 * height_div_percent) as f64/100.0),
		
		St::WordWrap => "break-word".to_string()
	    ],

	    // The text content
	    format!("{}", &instrument),

	    // Three states for a pedal
	    span![
		attrs![At::Width => "33%",
		       At::Class => 
		       if pedal_state == 'a' {
			   "pedal-a-selected"
		       }else{
			   "pedal-a"
		       },
		],
		"&nbsp;"
	    ],
	    span![
		attrs![At::Width => "33%",
		       At::Class => if pedal_state == 'b' {
			   "pedal-b-selected"
		       }else{
			   "pedal-b"
		       },
		],
		"&nbsp;"
	    ],
	    span![
		attrs![At::Width => "33%",
		       At::Class => if pedal_state == 'c' {
			   "pedal-c-selected"
		       }else{
			   "pedal-c"
		       },
		],
		"&nbsp;"
	    ],
	]
    ]
}

/// Called by `Seed` to initialise the application..  
fn init(url: Url, orders: &mut impl Orders<Msg>) -> Model {
    log!(my_now(), "Init: url: ", url);
    Model {
	instruments: Vec::new(), 
	pedal_state: 'a', // Arbitrary
	selected:None,
        sent_messages_count: 0,
        messages: Vec::new(),
        input_text: String::new(),
        input_binary: String::new(),
        web_socket: create_websocket(orders),
        web_socket_reconnector: None,
    }
}

/// Called when a message is received.  Adjust state in `model` and
/// respond to server messages
fn update(
    msg: Msg,
    mut model: &mut Model,
    orders: &mut impl Orders<Msg>
) {
    log!(my_now(), format!("update"));
    match msg {

	// Opened a websocked.  Send a message asking for data to
	// initialise the client
        Msg::WebSocketOpened => {
            log!(my_now(), "WebSocket connection is open now");
            model.web_socket_reconnector = None;

	    // Get the data needed to set up the client
	    let message_text = "INIT".to_string();
	    let m = shared::ClientMessage {
		text: message_text.clone()
	    };

            model.web_socket.send_json(&m).unwrap();
            model.input_text.clear();
            model.sent_messages_count += 1;
            log!(my_now(), message_text);

        }

	// The server has sent some information.
        Msg::TextMessageReceived(message) => {
            log!( my_now(), "Client received a text message",message.text);

	    // Split the server message by white space.  The first
	    // word is the command, it has no white space in it.  The
	    // names of instruments cannot have white space because of
	    // this.  It could be possible to reassemble the names
	    // over spaces using new lines, but simpler to not allow
	    // spaces in instrument names
	    let cmds:Vec<&str> = message.text.split_whitespace().collect();

	    match cmds[0] {

		// The data needed to establisg the client state.  The
		// selected instrument (in .Ready state), the possable
		// instruments
		"INIT" => {
		    assert!(cmds.len() > 2);
		    log!(my_now(), "Got INIT");
		    model.instruments.clear();
		    // The first line is the instrument that is selected
		    model.selected = Some(Selected {
			name: cmds[1].to_string(),
			state: SelectedState::Ready,
		    });
		    for i in 2..cmds.len() {
			log!(my_now(), format!("Got instrument {}", cmds[i]));
			model.instruments.push(cmds[i].to_string())
		    }			
		},

		// Pedal used on server
		"PEDALSTATE" => {
		    model.pedal_state = cmds[1].chars().nth(0).unwrap();
		},

		// Otherwise we are getting told which instrument has
		// been selected
		instrument => {
		    log!(my_now(), format!("Got instrument: {}", &instrument));
		    model.selected = Some(
			Selected {
			    name:instrument.to_string(),
			    state: SelectedState::Ready
			}
		    );
		},
	    }

	    // Why? AFAICT model::messages grows monotonically for no
	    // purpose
            model.messages.push(message.text);
	}
	
	// We do not use binary messages.  
	Msg::BinaryMessageReceived(message) => {
            log!(my_now(), "Client received binary message");
	    panic!("Binary message received: {:?}", message);
            //model.messages.push(message.text);
	}

	Msg::CloseWebSocket => {
            log!(my_now(), "Client received CloseWebsocket");
            model.web_socket_reconnector = None;
            model
		.web_socket
		.close(None, Some("user clicked Close button"))
		.unwrap();
	}

	Msg::WebSocketClosed(close_event) => {
            log!("==================");
            log!("WebSocket connection was closed:");
            log!("Clean:", close_event.was_clean());
            log!("Code:", close_event.code());
            log!("Reason:", close_event.reason());
            log!(my_now(), "==================");

            // Chrome doesn't invoke `on_error` when the connection is lost.
            if !close_event.was_clean() && model.web_socket_reconnector.is_none() {
		model.web_socket_reconnector = Some(
                    orders.stream_with_handle(streams::backoff(None, Msg::ReconnectWebSocket)),
		);
            }
	}

	Msg::WebSocketFailed => {
            log!(my_now(), "WebSocket failed");
            if model.web_socket_reconnector.is_none() {
		model.web_socket_reconnector = Some(
                    orders.stream_with_handle(streams::backoff(None, Msg::ReconnectWebSocket)),
		);
            }
	}

	Msg::ReconnectWebSocket(retries) => {
            log!(my_now(), "Reconnect attempt:", retries);
            model.web_socket = create_websocket(orders);
	}

	Msg::InputTextChanged(text) => {
            log!(my_now(), "Client received InputTextChanged");
            model.input_text = text;
	}

	Msg::InputBinaryChanged(text) => {
            log!(my_now(), "Client received InputBinaryChanged");
            model.input_binary = text;
	}

	Msg::SendMessage(msg) => {
	    // If `msg` is: "INSTR <instrument>" then we are telling
	    // the server to select that instrument so that instrument
	    // gets selected
            log!(my_now(), "Client received msg.text: {}", msg.text);
	    if msg.text.as_str().starts_with("INSTR ") {
		log!(my_now(), "msg.text[6..]: {}", msg.text[6..]);
		model.selected = Some(
		    Selected {
			name:msg.text[6..].to_string(),
			state: SelectedState::Initialising
		    }
		);
	    }
            model.web_socket.send_json(&msg).unwrap();
            model.input_text.clear();
            model.sent_messages_count += 1;
	}

	Msg::SendBinaryMessage(msg) => {
            let serialized = rmp_serde::to_vec(&msg).unwrap();
            model.web_socket.send_bytes(&serialized).unwrap();
            model.input_binary.clear();
            model.sent_messages_count += 1;
	}
    }
}

/// Updates the user interface
fn view(model: &Model) -> Vec<Node<Msg>> {
    
    // `body` is a convenience function to access the web_sys DOM
    // body. https://docs.rs/seed/0.8.0/seed/browser/util/fn.body.html
    body().style().set_css_text("height: 100%");

    let mut ret:Vec<Node<Msg>> = Vec::new();

    // If the client is talking to a server, only then can it have
    // meaningful existence
    if model.web_socket.state() == web_socket::State::Open {
	
	for i in model.instruments.iter() {
	    // log!(format!("{} View: Instrument: {}", my_now(), i));
	    ret.push(
		instrument_div(
		    i.clone(),
		    model.pedal_state,
		    1.0_f32/model.instruments.len() as f32,
		    &model.selected,
		)
	    );
        }
    } else {
        ret.push(div![p![em!["Connecting or closed"]]]);
    }
    ret
}

#[wasm_bindgen(start)]
pub fn start() {
    App::start(
	// The generated HTML will attach itself to a <section
	// id=<section id="app"> Unsure if it needs to be a section...
	"app",

	// Functions for running the application.  `init` is run once
	// at initialisation, `update` is called when a message
	// received and `view` is called to update the HTML5 UI
	init, update, view);
}
