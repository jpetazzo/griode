#![warn(clippy::all)]
use actix_web::{get, post, web, App, HttpResponse, HttpServer, Responder};
use std::process::Command;

// Endpoints
#[get("/")]
async fn hello() -> impl Responder {
    HttpResponse::Ok().body("Hello world!")
}

#[post("/echo")]
async fn echo(req_body: String) -> impl Responder {
    HttpResponse::Ok().body(req_body)
}

// `/hey`
async fn manual_hello() -> impl Responder {
    HttpResponse::Ok().body("Hey there!")
}

async fn list_jack_ports() -> impl Responder {
    let jack_ports = get_jack_ports().unwrap();
    HttpResponse::Ok().body(jack_ports)
}

// Commands to execute
fn get_jack_ports() -> std::io::Result<Vec<u8>> {
    let output = Command::new("jack_lsp").arg("-cpt").output().unwrap();
    Ok(output.stdout)
}
fn list_songs()  -> std::io::Result<Vec<u8>> {
    
}
// 

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    HttpServer::new(|| {
        App::new()
            .service(hello)
            .service(echo)
            .route("/hey", web::get().to(manual_hello))
	    .route("/jack", web::get().to(list_jack_ports))
    })
    .bind("0.0.0.0:8080")?
    .run()
    .await
}
