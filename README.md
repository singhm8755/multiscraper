cat > README.md << 'EOF'
# Multi-Scraper Tool

A Flask-based web scraping application for extracting images, links, analyzing SEO metrics, and comparing product prices across UK retailers.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-2.3.0-green)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-3.0.3-orange)

## Features

- **🖼️ Image Extractor** - Scrape and download images from any website with alt text preservation
- **🔗 Link Extractor** - Extract all links and categorize as internal/external
- **📊 SEO Analyzer** - Analyze on-page SEO with scoring system (A-F grades)
- **🛒 Product Comparison** - Compare UK retailer prices (Amazon, Currys, John Lewis, Argos, eBay)
- **📈 History Dashboard** - Track all scraping jobs with timestamps
- **📉 Analytics** - View usage statistics and trends

## Quick Start

### Installation

```bash
git clone https://github.com/singhm8755/multiscraper.git
cd multiscraper
pip install -r requirements.txt
```

### Setup Environment

```bash
cp .env.example .env
```

### Run the Application

```bash
python app.py
```

Visit `http://localhost:5000` in your browser.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Flask 2.3.0 |
| Database | SQLite + SQLAlchemy |
| Web Scraping | BeautifulSoup4, Requests |
| Frontend | HTML5, CSS3, JavaScript |

## Project Structure
multiscraper/
├── app.py # Main Flask application
├── requirements.txt # Python dependencies
├── .env.example # Environment variables template
├── README.md # This file
├── templates/ # HTML templates
│ ├── index.html # Home page
│ ├── image_extractor.html # Image scraper UI
│ ├── link_extractor.html # Link extractor UI
│ ├── seo_analyzer.html # SEO analysis UI
│ ├── product_comparison.html # Price comparison UI
│ ├── history.html # Job history dashboard
│ └── statistics.html # Analytics dashboard
└── static/ # Static assets
├── css/ # Stylesheets
├── js/ # JavaScript files
└── images/ # Downloaded images (git ignored)


## Database Models

- **ScrapingJob** - Stores job metadata (URL, tool, status, results count)
- **ScrapedImage** - Tracks downloaded images
- **ExtractedLink** - Stores extracted links with metadata
- **ProductComparison** - Caches product data from UK retailers

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/scrape-images` | POST | Extract images from URL |
| `/extract-links` | POST | Extract links from URL |
| `/analyze-seo` | POST | Analyze SEO metrics |
| `/api/compare-products` | POST | Compare product prices |
| `/api/history` | GET | Get scraping history |
| `/api/stats` | GET | Get usage statistics |

## Features in Detail

### SEO Analyzer
Rates pages on:
- Title tag (30-60 characters optimal)
- Meta description (120-160 characters optimal)
- Headings (H1, H2 structure)
- Image alt text coverage
- Internal/external links
- Content length (300+ words recommended)

### Product Comparison
Aggregates data from:
- Amazon UK
- Currys
- John Lewis
- Argos
- eBay UK

Data includes price, rating, stock status, and delivery info.

## Error Handling

- URL validation before scraping
- Request timeouts (8-10 seconds)
- Database transaction rollback on error
- Comprehensive logging
- User-friendly error messages

## Future Enhancements

- [ ] Async scraping with Celery
- [ ] Advanced filtering in history
- [ ] Custom export formats (PDF, Excel)
- [ ] Price alert notifications
- [ ] Scheduled scraping jobs

## Security Notes

- `.env` file not tracked in git (use `.env.example`)
- Max upload size: 16MB
- Filename sanitization for downloads
- CSRF protection ready (add to templates)

## Contributing

Feel free to fork and submit pull requests!

## License

MIT License

---

**Made with ❤️ for portfolio demonstration**
EOF
