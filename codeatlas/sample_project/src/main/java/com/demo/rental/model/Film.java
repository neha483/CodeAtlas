package com.demo.rental.model;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * JPA entity representing a rentable film title in the catalogue.
 */
@Entity
@Table(name = "film")
public class Film {

    @Id
    private Long filmId;
    private String title;
    private String description;
    private Integer releaseYear;
    private Double rentalRate;

    public Long getFilmId() {
        return filmId;
    }

    public void setFilmId(Long filmId) {
        this.filmId = filmId;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public Integer getReleaseYear() {
        return releaseYear;
    }

    public void setReleaseYear(Integer releaseYear) {
        this.releaseYear = releaseYear;
    }

    public Double getRentalRate() {
        return rentalRate;
    }

    public void setRentalRate(Double rentalRate) {
        this.rentalRate = rentalRate;
    }
}
