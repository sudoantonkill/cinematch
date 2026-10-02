import { useEffect, useState } from 'react'
import './App.css'

const API_URL = 'http://localhost:8000'

function MovieCard({ movie, selected, onSelect, recommendation }) {
  const genres = movie.genres?.split('|').filter((genre) => genre !== '(no genres listed)').slice(0, 2) ?? []
  return (
    <button className={`movie-card ${selected ? 'selected' : ''} ${recommendation ? 'recommendation' : ''}`} onClick={() => onSelect?.(movie)}>
      <span className="poster-art" aria-hidden="true"><i></i><b></b>{movie.posterUrl && <img src={movie.posterUrl} alt="" loading="lazy" onError={(event) => { event.currentTarget.style.display = 'none' }} />}</span>
      <span className="movie-copy">
        <span className="movie-title">{movie.title}</span>
        <span className="genres">{genres.map((genre) => <em key={genre}>{genre}</em>)}</span>
        {recommendation && <><span className="why-selected"><b>Why this pick</b>{movie.whySelected}</span><ul className="rec-points">{movie.highlights?.map((point) => <li key={point}>{point}</li>)}</ul></>}
      </span>
      {recommendation ? <span className="match">{movie.match}%<small> match</small></span> : <span className="add-mark">{selected ? '✓' : '+'}</span>}
    </button>
  )
}

function App() {
  const [query, setQuery] = useState('')
  const [movies, setMovies] = useState([])
  const [featured, setFeatured] = useState([])
  const [selected, setSelected] = useState([])
  const [recommendations, setRecommendations] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [discovering, setDiscovering] = useState(false)
  const [error, setError] = useState('')

  const fetchMovies = async (search = '', signal) => {
    const response = await fetch(`${API_URL}/movies?q=${encodeURIComponent(search)}&limit=18`, { signal })
    if (!response.ok) throw new Error('The catalogue could not be reached. Is the Spark API running?')
    const data = await response.json()
    setMovies(data.movies)
  }

  useEffect(() => {
    const boot = async () => {
      let ready = false
      for (let attempt = 0; attempt < 45; attempt += 1) {
        try {
          const response = await fetch(`${API_URL}/health`)
          if (response.ok && (await response.json()).ready) {
            ready = true
            break
          }
        } catch {
          // Spark owns startup; retry quietly while it builds the model.
        }
        await new Promise((resolve) => setTimeout(resolve, 1000))
      }
      try {
        if (!ready) throw new Error('CineMatch could not start. Check that the backend and Java are installed, then refresh.')
        const [featuredResponse, metricsResponse] = await Promise.all([fetch(`${API_URL}/featured`), fetch(`${API_URL}/metrics`)])
        if (!featuredResponse.ok || !metricsResponse.ok) throw new Error('CineMatch could not load its catalogue. Please refresh.')
        setFeatured((await featuredResponse.json()).movies)
        setMetrics(await metricsResponse.json())
        await fetchMovies()
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    boot()
  }, [])

  useEffect(() => {
    if (loading) return undefined
    const controller = new AbortController()
    const timer = setTimeout(() => {
      fetchMovies(query, controller.signal).catch((err) => {
        if (err.name !== 'AbortError') setError(err.message)
      })
    }, 220)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query, loading])

  const toggleMovie = (movie) => {
    setError('')
    setRecommendations([])
    setSelected((current) => current.some((item) => item.movieId === movie.movieId)
      ? current.filter((item) => item.movieId !== movie.movieId)
      : current.length < 5 ? [...current, movie] : current)
  }

  const discover = async () => {
    if (!selected.length) return
    setDiscovering(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/discover`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ movie_ids: selected.map((movie) => movie.movieId), num_recommendations: 12 }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Discovery failed. Please try another title.')
      setRecommendations(data.recommendations)
      document.getElementById('discoveries')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    } catch (err) {
      setError(err.message)
    } finally {
      setDiscovering(false)
    }
  }

  const isSelected = (movie) => selected.some((item) => item.movieId === movie.movieId)

  return (
    <div className="app-shell">
      <nav><a className="brand" href="#top"><span>◒</span> CINE<span>MATCH</span></a><p>Made for the curious</p><a className="nav-link" href="#how">How it works <span>↗</span></a></nav>
      <main id="top">
        <section className="hero">
          <div className="eyebrow"><span></span> A SPARK-POWERED TASTE ENGINE</div>
          <h1>Your next <i>favourite</i><br />is already in the data.</h1>
          <p>Choose a few films you love. Our collaborative filtering model maps the hidden patterns in taste to find what should come next.</p>
          <div className="hero-rule"><span>01</span><b></b><span>DISCOVER YOUR NEXT OBSESSION</span></div>
        </section>

        <section className="taste-studio" aria-label="Movie discovery studio">
          <div className="studio-head"><div><p className="section-kicker">BUILD YOUR TASTE PROFILE</p><h2>What moves you?</h2></div><p>Select up to 5 films. One is enough to start, but a few make the signal richer.</p></div>
          <div className="search-box"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search a title, director, or genre" aria-label="Search movies" /><kbd>⌘ K</kbd></div>
          {error && <div className="error-banner">{error}</div>}
          <div className="selected-row">
            <span className="selected-label">YOUR PICKS <b>{selected.length}/5</b></span>
            <div className="chips">{selected.length ? selected.map((movie) => <button className="chip" key={movie.movieId} onClick={() => toggleMovie(movie)}>{movie.title} <b>×</b></button>) : <span className="empty-picks">Nothing selected yet — start with a film you can’t stop thinking about.</span>}</div>
            <button className="discover-button" disabled={!selected.length || discovering} onClick={discover}>{discovering ? 'Reading the room…' : 'Find my next film'} <span>→</span></button>
          </div>
          <div className="catalog-head"><p>{query ? 'SEARCH RESULTS' : 'EXPLORE THE CATALOGUE'}</p><span>{query ? `${movies.length} matches` : '18 handpicked starts'}</span></div>
          <div className="movie-grid">{loading ? <div className="loading-grid"><span className="loading-dot"></span>Preparing your recommendations…</div> : movies.length ? movies.map((movie) => <MovieCard key={movie.movieId} movie={movie} selected={isSelected(movie)} onSelect={toggleMovie} />) : <div className="loading-grid">No films found for “{query}”. Try a title or genre.</div>}</div>
        </section>

        {!query && <section className="featured"><div className="section-title"><div><p className="section-kicker">START HERE</p><h2>Universally adored.<br /><i>Distinctly yours.</i></h2></div><p>High-rated films from the MovieLens community — a good first ingredient for your taste profile.</p></div><div className="featured-grid">{featured.slice(0, 6).map((movie) => <MovieCard key={movie.movieId} movie={movie} selected={isSelected(movie)} onSelect={toggleMovie} />)}</div></section>}

        {recommendations.length > 0 && <section id="discoveries" className="discoveries"><div className="results-intro"><p className="section-kicker">YOUR TASTE, DECODED</p><h2>The next chapter<br /><i>starts here.</i></h2><p>Each match includes the signal behind it and three genre-aware reasons it belongs in your queue.</p></div><div className="results-grid">{recommendations.map((movie, index) => <div className="result-wrap" key={movie.movieId}><span className="result-number">{String(index + 1).padStart(2, '0')}</span><MovieCard movie={movie} recommendation onSelect={() => toggleMovie(movie)} /></div>)}</div></section>}

        <section id="how" className="proof"><div><p className="section-kicker">NOT A GUESS</p><h2>Built on behaviour,<br />not buzz.</h2></div><div className="proof-copy"><p>CineMatch learns from real rating patterns, rather than merely matching genre tags. Spark’s ALS model compresses millions of preference signals into a shared map of cinematic taste.</p><div className="stats"><span><b>{metrics ? metrics.rmse.toFixed(3) : '—'}</b> RMSE</span><span><b>{metrics ? '100K+' : '—'}</b> ratings</span><span><b>ALS</b> model</span></div></div></section>
      </main>
      <footer><a className="brand" href="#top"><span>◒</span> CINE<span>MATCH</span></a><p>Collaborative filtering with Apache Spark · MovieLens dataset</p><a href="#top">Back to top ↑</a></footer>
    </div>
  )
}

export default App
