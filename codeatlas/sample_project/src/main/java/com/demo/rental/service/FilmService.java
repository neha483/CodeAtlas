package com.demo.rental.service;

import com.demo.rental.model.Film;
import com.demo.rental.repository.FilmRepository;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Optional;

/**
 * Business logic for the film catalogue: validation, filtering and pricing
 * rules sit here rather than in the controller or repository.
 */
@Service
public class FilmService {

    private final FilmRepository filmRepository;

    public FilmService(FilmRepository filmRepository) {
        this.filmRepository = filmRepository;
    }

    public List<Film> listAll() {
        return filmRepository.findAll();
    }

    public Optional<Film> findById(Long id) {
        if (id == null || id < 0) {
            throw new IllegalArgumentException("Film id must be a positive value");
        }
        return filmRepository.findById(id);
    }

    public List<Film> searchByTitle(String fragment) {
        if (fragment == null || fragment.isBlank()) {
            return listAll();
        }
        return filmRepository.findByTitleContainingIgnoreCase(fragment.trim());
    }

    /**
     * Apply a percentage discount to a film's rental rate, clamped to zero.
     */
    public double discountedRate(Film film, double percent) {
        if (film == null) {
            throw new IllegalArgumentException("Film must not be null");
        }
        double rate = film.getRentalRate() == null ? 0.0 : film.getRentalRate();
        if (percent <= 0) {
            return rate;
        }
        double discounted = rate - (rate * percent / 100.0);
        return discounted < 0 ? 0.0 : discounted;
    }
}
