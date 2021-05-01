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

fn update(msg: Msg, mut model: &mut Model, orders: &mut impl Orders<Msg>) {
    log!(my_now(), format!("update"));
    match msg {
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

        Msg::TextMessageReceived(message) => {
            log!( my_now(), "Client received a text message",message.text);

	    // FIXME This should split on new lines so instruments can
	    // have spaces in their names.
	    let cmds:Vec<&str> = message.text.split_whitespace().collect();
	    match cmds[0] {
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

		key => {
		    log!(my_now(), format!("Got key: {}", &key));
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
            log!(my_now(), "Client received binary message");
            model.messages.push(message.text);
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

fn view(model: &Model) -> Vec<Node<Msg>> {
    
    // log!(my_now(), format!("{} View.  instruments len: {}",
    // 		 my_now(), model.instruments.len()));


    // `body` is a convenience function to access the web_sys DOM
    // body. https://docs.rs/seed/0.8.0/seed/browser/util/fn.body.html
    body().style().set_css_text("height: 100%");

    let mut ret:Vec<Node<Msg>> = Vec::new();

    if model.web_socket.state() == web_socket::State::Open {
	
	for i in model.instruments.iter() {
	    // log!(format!("{} View: Instrument: {}", my_now(), i));
	    ret.push(
		instrument_div(
		    i.clone(),
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


fn instrument_div(instrument: String,
	    height:f32, // Proportion of page
	    selected:&Option<Selected>) -> Node<Msg> {

    // log!(my_now(), format!("{} instrument_div({})", my_now(), instrument));

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
    
    // For CSS height is in percent.  
    let height_div_percent = (100.0 * height).floor();

    // To send on click
    let message = format!("INSTR {}", &instrument);
    
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
		// log!(my_now(), my_now(), "Ev::Click Setup", instrument);
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
		// The whole page is 10em
		St::FontSize => format!("{}em", (10.0 * height_div_percent) as f64/100.0),
		St::WordWrap => "break-word".to_string()
	    ],
	    format!("{}", &instrument),
	],
    ]
}

// ------ ------
//     Start
// ------ ------

#[wasm_bindgen(start)]
pub fn start() {
    App::start("app", init, update, view);
}
