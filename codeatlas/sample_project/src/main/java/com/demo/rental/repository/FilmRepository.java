package com.demo.rental.repository;

import com.demo.rental.model.Film;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * Spring Data repository for {@link Film} aggregate access.
 */
@Repository
public interface FilmRepository extends JpaRepository<Film, Long> {

    List<Film> findByReleaseYear(Integer releaseYear);

    List<Film> findByTitleContainingIgnoreCase(String fragment);
}
