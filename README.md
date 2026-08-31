# Multi-Scraper Tool

A Flask-based web scraping application for extracting images, links, analyzing SEO, and comparing product prices across UK retailers.

## Features
- **Image Extractor** - Scrape images from any website
- **Link Extractor** - Extract and categorize links (internal/external)
- **SEO Analyzer** - Get SEO scores with detailed metrics
- **Product Comparison** - Compare prices across Amazon UK, Currys, John Lewis, Argos, eBay
- **History & Stats** - Track all scraping jobs with analytics dashboard

## Setup

```bash
pip install -r requirements.txt
python app3.py
```

Visit `http://localhost:5000`

## Tech Stack
- Flask + SQLAlchemy
- BeautifulSoup4
- SQLite
- Requests

## Project Structure

Multi_Scraper/
├── app3.py # Main Flask application
├── requirements.txt # Python dependencies
├── templates/ # HTML templates
└── static/ # CSS, JS, images
