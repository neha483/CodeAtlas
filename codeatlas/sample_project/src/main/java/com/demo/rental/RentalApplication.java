package com.demo.rental;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Application entry point. Boots the Spring context and starts the embedded
 * web server exposing the film catalogue REST API.
 */
@SpringBootApplication
public class RentalApplication {

    public static void main(String[] args) {
        SpringApplication.run(RentalApplication.class, args);
    }
}
