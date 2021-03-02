use seed::{prelude::*, *};
use std::rc::Rc;
mod shared;
//use std::time::SystemTime;
use chrono::{Local, DateTime};
const WS_URL: &str = "ws://patchbox.local:9000/ws";

// The selected instrument is either selected or ready
#[derive(PartialEq)]
enum SelectedState {
    Initialising,
    Ready,
}

// For a selected instrument associate its state
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
    
    sent_messages_count: usize,
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

// The App init function. 
fn init(url: Url, orders: &mut impl Orders<Msg>) -> Model {
    log!(my_now(), "Init: url: ", url);
    Model {
	instruments: Vec::new(), 
	selected:None,
        sent_messages_count: 0,
        messages: Vec::new(),
        input_text: String::new(),
        input_binary: String::new(),
        web_socket: create_websocket(orders),
        web_socket_reconnector: None,
    }
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

fn update(msg: Msg, mut model: &mut Model, orders: &mut impl Orders<Msg>) {
    match msg {
        Msg::WebSocketOpened => {
            model.web_socket_reconnector = None;
            log!(my_now(), "WebSocket connection is open now");

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

        Msg::TextMessageReceived(message) => {
            log!( my_now(), "Client received a text message",message.text);
	    let cmds:Vec<&str> = message.text.split_whitespace().collect();
	    match cmds[0] {
		"INIT" => {
		    log!("Got INIT");
		    model.instruments.clear();
		    for i in 1..cmds.len() {
			log!(format!("Got instrument {}", cmds[i]));
			model.instruments.push(cmds[i].to_string())
		    }			
		},
		key => {
		    log!(format!("Got key: {}", &key));
		    model.selected = Some(
			Selected {
			    name:key.to_string(),
			    state: SelectedState::Ready
			}
		    );
		},
	    }
            model.messages.push(message.text);
	}
	Msg::BinaryMessageReceived(message) => {
            log!("Client received binary message");
            model.messages.push(message.text);
	}
	Msg::CloseWebSocket => {
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
            log!("==================");

            // Chrome doesn't invoke `on_error` when the connection is lost.
            if !close_event.was_clean() && model.web_socket_reconnector.is_none() {
		model.web_socket_reconnector = Some(
                    orders.stream_with_handle(streams::backoff(None, Msg::ReconnectWebSocket)),
		);
            }
	}
	Msg::WebSocketFailed => {
            log!("WebSocket failed");
            if model.web_socket_reconnector.is_none() {
		model.web_socket_reconnector = Some(
                    orders.stream_with_handle(streams::backoff(None, Msg::ReconnectWebSocket)),
		);
            }
	}
	Msg::ReconnectWebSocket(retries) => {
            log!("Reconnect attempt:", retries);
            model.web_socket = create_websocket(orders);
	}
	Msg::InputTextChanged(text) => {
            model.input_text = text;
	}
	Msg::InputBinaryChanged(text) => {
            model.input_binary = text;
	}
	Msg::SendMessage(msg) => {
	    // If `msg` is: "INSTR <instrument>" then we are telling
	    // the server to select that instrument so that instrument
	    // gets selected
	    if msg.text.as_str().starts_with("INSTR ") {
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

fn create_websocket(orders: &impl Orders<Msg>) -> WebSocket {
    let msg_sender = orders.msg_sender();

    WebSocket::builder(WS_URL, orders)
        .on_open(|| Msg::WebSocketOpened)
        .on_message(move |msg| decode_message(msg, msg_sender))
        .on_close(Msg::WebSocketClosed)
        .on_error(|| Msg::WebSocketFailed)
        .build_and_open()
        .unwrap()
}

fn decode_message(message: WebSocketMessage, msg_sender: Rc<dyn Fn(Option<Msg>)>) {
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

            let msg: shared::ServerMessage = rmp_serde::from_slice(&bytes).unwrap();
            msg_sender(Some(Msg::BinaryMessageReceived(msg)));
        });
    }
}

// ------ ------
//     View
// ------ ------
fn main_div(instrument: String, height:f32, selected:bool) -> Node<Msg> {
    log!(format!("{} main_div({})", my_now(), instrument));

    // For CSS height is in percent.  
    let height_div_percent = (100.0 * height).floor();

    // To send on click
    let message = format!("INSTR {}", &instrument);
    let class = if selected {
	"selected"
    }else{
	"unselected"
    };
    
    div![
	//
	attrs![
	    At::Height => percent(33),
	    At::Class => class,
	],
	style![
	    St::Width => "100%",
	    St::Height => format!("{}%", height_div_percent).as_str(),
	    St::Display => "block",
	    St::Border => "1px solid red",
	    St::TextAlign => "center",
	],
        ev(
	    Ev::Click,
	    {
		log!(my_now(), "Ev::Click Setup", instrument);
		let instrument_clone = instrument.clone();
		// Return the closure to execute if there is a click
		move |_| {
		    log!(my_now(), "Ev::Click ", instrument_clone);		    
		    Msg::SendMessage(shared::ClientMessage { text: message })
		}
            }
	),
	span![
	    C!["instrument_name"],
	    style![
		St::FontSize => format!("{}vh", height_div_percent),
	    ],
	    format!("{}", &instrument),
	],
    ]
}

fn view(model: &Model) -> Vec<Node<Msg>> {
    
    log!(format!("{} View.  instruments len: {}",
		 my_now(), model.instruments.len()));


    // `body` is a convenience function to access the web_sys DOM
    // body. https://docs.rs/seed/0.8.0/seed/browser/util/fn.body.html
    body().style().set_css_text("height: 100%");

    let mut ret:Vec<Node<Msg>> = Vec::new();

    if model.web_socket.state() == web_socket::State::Open {
	
	for i in model.instruments.iter() {
	    let selected =
		if model.selected.is_some() &&
		model.selected.as_ref().unwrap().state ==
		SelectedState::Ready &&
		&model.selected.as_ref().unwrap().name == i {
		    true
		} else {
		    false
		};
	    log!(format!("{} View: Instrument: {}", my_now(), i));
	    ret.push(
		main_div(
		    i.clone(),
		    1.0_f32/model.instruments.len() as f32,
		    selected,
		)
	    );
        }
    } else {
        ret.push(div![p![em!["Connecting or closed"]]]);
    }
    ret
}

// ------ ------
//     Start
// ------ ------

#[wasm_bindgen(start)]
pub fn start() {
    App::start("app", init, update, view);
}
