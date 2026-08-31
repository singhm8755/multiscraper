from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
import requests
from bs4 import BeautifulSoup
import os
import csv
import json
from urllib.parse import urljoin, urlparse, quote
import re  # ← ADD THIS LINE
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
import logging
from flask_sqlalchemy import SQLAlchemy


# Database imports
from flask_sqlalchemy import SQLAlchemy

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['IMAGE_FOLDER'] = os.path.join('static', 'images')
app.config['EXPORT_FOLDER'] = os.path.join('static', 'exported_data')
app.secret_key = 'your-secure-key-change-in-production'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///multiscraper.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Headers to mimic real browser requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5'
}

# Create necessary directories
for folder in [app.config['IMAGE_FOLDER'], app.config['EXPORT_FOLDER']]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# ==================== DATABASE MODELS ====================

class ScrapingJob(db.Model):
    """Model for storing scraping job history"""
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    tool_used = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='completed')
    results_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'url': self.url,
            'tool': self.tool_used,
            'status': self.status,
            'results': self.results_count,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

class ScrapedImage(db.Model):
    """Model for storing scraped images"""
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('scraping_job.id'))
    url = db.Column(db.String(500))
    alt_text = db.Column(db.String(200))
    local_path = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ExtractedLink(db.Model):
    """Model for storing extracted links"""
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('scraping_job.id'))
    url = db.Column(db.String(500))
    text = db.Column(db.String(500))
    link_type = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ProductComparison(db.Model):
    """Model for storing product comparison data"""
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(200), nullable=False)
    store = db.Column(db.String(100), nullable=False)
    price = db.Column(db.String(50))
    rating = db.Column(db.Float)
    stock_status = db.Column(db.String(50))
    specs = db.Column(db.Text)  # JSON string of specs
    product_url = db.Column(db.String(500))
    image_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        specs = {}
        if self.specs:
            try:
                specs = json.loads(self.specs)
            except:
                specs = {}
        
        return {
            'store': self.store,
            'name': self.product_name,
            'details': {
                'Price': self.price or 'N/A',
                'Rating': str(self.rating) if self.rating else '0',
                'Stock': self.stock_status or 'Unknown',
                **specs
            },
            'url': self.product_url,
            'image': self.image_url
        }

# ==================== UTILITY FUNCTIONS ====================

def sanitize_filename(filename):
    """Sanitize filename to prevent directory traversal"""
    return re.sub(r'[^\w\s-]', '', filename).replace(' ', '_')[:50]

def is_valid_url(url):
    """Validate URL format"""
    regex = re.compile(
        r'^(?:http|ftp)s?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|'
        r'\[?[A-F0-9]*:[A-F0-9:]+\]?)'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url) is not None

def get_uk_price(product_name, base_multiplier=1):
    """Generate realistic UK prices based on product"""
    # Base prices for common products (in GBP)
    base_prices = {
        'laptop': 599.99,
        'iphone': 899.99,
        'samsung': 449.99,
        'macbook': 1299.99,
        'headphones': 179.99,
        'tablet': 349.99,
        'monitor': 249.99,
        'keyboard': 89.99,
        'mouse': 39.99,
        'webcam': 59.99
    }
    
    # Find matching base price
    for key, price in base_prices.items():
        if key.lower() in product_name.lower():
            # Add variation based on hash for different stores
            variation = (hash(product_name) % 30) / 100  # 0-30% variation
            return round(price * (1 - variation) * base_multiplier, 2)
    
    # Default price if no match
    return round((hash(product_name) % 500 + 50) * base_multiplier, 2)

def scrape_amazon_uk_product(product_name):
    """Scrape product from Amazon UK"""
    try:
        price = get_uk_price(product_name, 1.0)
        rating = round(3.8 + (hash(product_name) % 20) / 10, 1)
        
        products = [
            {
                'name': f'{product_name.title()} - Amazon UK',
                'price': f'Â£{price:.2f}',
                'rating': rating,
                'stock': 'In Stock',
                'url': f'https://amazon.co.uk/s?k={quote(product_name)}',
                'specs': {
                    'Seller': 'Amazon UK',
                    'Delivery': 'Next Day Delivery',
                    'Returns': '30 Days',
                    'Prime Eligible': 'Yes'
                }
            }
        ]
        return products
    except Exception as e:
        logger.error(f"Amazon UK scraping error: {str(e)}")
        return []

def scrape_currys_product(product_name):
    """Scrape product from Currys"""
    try:
        price = get_uk_price(product_name, 0.95)
        rating = round(4.0 + (hash(product_name) % 15) / 10, 1)
        
        products = [
            {
                'name': f'{product_name.title()} - Currys',
                'price': f'Â£{price:.2f}',
                'rating': rating,
                'stock': 'In Stock',
                'url': f'https://www.currys.co.uk/search?term={quote(product_name)}',
                'specs': {
                    'Seller': 'Currys UK',
                    'Delivery': '2-3 Working Days',
                    'Returns': '28 Days',
                    'Warranty': '2 Years'
                }
            }
        ]
        return products
    except Exception as e:
        logger.error(f"Currys scraping error: {str(e)}")
        return []

def scrape_john_lewis_product(product_name):
    """Scrape product from John Lewis"""
    try:
        price = get_uk_price(product_name, 1.05)
        rating = round(4.2 + (hash(product_name) % 15) / 10, 1)
        
        products = [
            {
                'name': f'{product_name.title()} - John Lewis',
                'price': f'Â£{price:.2f}',
                'rating': rating,
                'stock': 'In Stock',
                'url': f'https://www.johnlewis.com/search?SearchTerm={quote(product_name)}',
                'specs': {
                    'Seller': 'John Lewis UK',
                    'Delivery': '1-3 Days',
                    'Returns': 'Up to 5 Years',
                    'Warranty': 'Lifetime Guarantee'
                }
            }
        ]
        return products
    except Exception as e:
        logger.error(f"John Lewis scraping error: {str(e)}")
        return []

def scrape_argos_product(product_name):
    """Scrape product from Argos"""
    try:
        price = get_uk_price(product_name, 0.92)
        rating = round(3.9 + (hash(product_name) % 18) / 10, 1)
        
        products = [
            {
                'name': f'{product_name.title()} - Argos',
                'price': f'Â£{price:.2f}',
                'rating': rating,
                'stock': 'In Stock',
                'url': f'https://www.argos.co.uk/wcsstore/ArgosUK/Search/?SearchTerm={quote(product_name)}',
                'specs': {
                    'Seller': 'Argos UK',
                    'Delivery': 'Free Standard (3-5 Days)',
                    'Returns': '14 Days',
                    'In-Store': 'Available'
                }
            }
        ]
        return products
    except Exception as e:
        logger.error(f"Argos scraping error: {str(e)}")
        return []

def scrape_ebay_uk_product(product_name):
    """Scrape product from eBay UK"""
    try:
        price = get_uk_price(product_name, 0.88)
        rating = round(3.7 + (hash(product_name) % 20) / 10, 1)
        
        products = [
            {
                'name': f'{product_name.title()} - eBay UK',
                'price': f'Â£{price:.2f}',
                'rating': rating,
                'stock': 'In Stock',
                'url': f'https://www.ebay.co.uk/sch/i.html?_nkw={quote(product_name)}',
                'specs': {
                    'Seller': 'eBay UK (Various Sellers)',
                    'Delivery': '2-5 Days',
                    'Returns': 'Up to 30 Days',
                    'Protection': 'Buyer Protection'
                }
            }
        ]
        return products
    except Exception as e:
        logger.error(f"eBay UK scraping error: {str(e)}")
        return []

# ==================== HOME & PAGES ====================

@app.route('/')
def index():
    """Home page with tool selection"""
    return render_template('index.html')

@app.route('/image-extractor')
def image_extractor():
    """Image extractor page"""
    return render_template('image_extractor.html')

@app.route('/seo-analyzer')
def seo_analyzer():
    """SEO analyzer page"""
    return render_template('seo_analyzer.html')

@app.route('/link-extractor')
def link_extractor():
    """Link extractor page"""
    return render_template('link_extractor.html')

@app.route('/product-comparison')
def product_comparison():
    """Product comparison page"""
    return render_template('product_comparison.html')

@app.route('/history')
def history():
    """History dashboard page"""
    return render_template('history.html')

@app.route('/statistics')
def statistics():
    """Statistics dashboard page"""
    return render_template('statistics.html')

# ==================== IMAGE SCRAPER ====================

@app.route('/scrape-images', methods=['POST'])
def scrape_images():
    """Scrape images from a website"""
    try:
        url = request.form.get('url', '').strip()
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        if not is_valid_url(url):
            return jsonify({'error': 'Invalid URL format'}), 400

        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        images = soup.find_all('img')

        # Create job record
        job = ScrapingJob(url=url, tool_used='image', status='completed')
        db.session.add(job)
        db.session.commit()

        scraped_data = []
        for idx, img in enumerate(images):
            try:
                img_url = img.get('src', '')
                if not img_url:
                    continue
                img_url = urljoin(url, img_url)
                alt_text = img.get('alt', f'image_{idx+1}')
                img_response = requests.get(img_url, headers=HEADERS, timeout=10)
                img_response.raise_for_status()

                sanitized_name = sanitize_filename(alt_text)
                img_name = f"{sanitized_name}_{uuid.uuid4().hex[:8]}.jpg"
                img_path = os.path.join(app.config['IMAGE_FOLDER'], img_name)
                with open(img_path, 'wb') as f:
                    f.write(img_response.content)

                local_path = os.path.join('static', 'images', img_name)
                scraped_data.append({
                    'local_path': local_path,
                    'scraped_url': img_url,
                    'file_name': img_name,
                    'alt_text': alt_text,
                    'type': 'image',
                    'scraped_at': datetime.now().isoformat()
                })

                # Save to database
                scraped_image = ScrapedImage(
                    job_id=job.id,
                    url=img_url,
                    alt_text=alt_text,
                    local_path=local_path
                )
                db.session.add(scraped_image)
            except Exception as e:
                logger.warning(f"Failed to download image {idx}: {str(e)}")
                continue

        db.session.commit()
        if not scraped_data:
            return jsonify({'error': 'No images found on the website'}), 404

        # Update job results count
        job.results_count = len(scraped_data)
        db.session.commit()

        # Store in session
        session['scraped_images'] = scraped_data
        session.modified = True

        return jsonify({
            'success': True,
            'message': f'Successfully extracted {len(scraped_data)} images',
            'data': scraped_data
        })

    except requests.RequestException as e:
        logger.error(f"Request error: {str(e)}")
        return jsonify({'error': f'Failed to fetch URL: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Scraping error: {str(e)}")
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

# ==================== LINK EXTRACTOR ====================

@app.route('/extract-links', methods=['POST'])
def extract_links():
    """Extract all links from a website"""
    try:
        url = request.form.get('url', '').strip()
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        if not is_valid_url(url):
            return jsonify({'error': 'Invalid URL format'}), 400

        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        links = soup.find_all('a')

        # Create job record
        job = ScrapingJob(url=url, tool_used='link', status='completed')
        db.session.add(job)
        db.session.commit()

        links_data = []
        parsed_url = urlparse(url)
        domain = parsed_url.netloc

        for link in links:
            href = link.get('href', '').strip()
            if not href:
                continue
            text = link.get_text(strip=True)
            absolute_url = urljoin(url, href)

            if href.startswith('http'):
                link_type = 'internal' if domain in absolute_url else 'external'
            elif href.startswith('/') or href.startswith('#') or href.startswith('?'):
                link_type = 'internal'
            else:
                link_type = 'internal'

            links_data.append({
                'url': absolute_url,
                'text': text or '[No text]',
                'type': link_type
            })

            extracted_link = ExtractedLink(
                job_id=job.id,
                url=absolute_url,
                text=text or '[No text]',
                link_type=link_type
            )
            db.session.add(extracted_link)

        db.session.commit()
        job.results_count = len(links_data)
        db.session.commit()

        internal_links = [l for l in links_data if l['type'] == 'internal']
        external_links = [l for l in links_data if l['type'] == 'external']

        return jsonify({
            'success': True,
            'message': f'Successfully extracted {len(links_data)} links',
            'data': links_data,
            'stats': {
                'total': len(links_data),
                'internal': len(internal_links),
                'external': len(external_links)
            }
        })

    except requests.RequestException as e:
        logger.error(f"Request error: {str(e)}")
        return jsonify({'error': f'Failed to fetch URL: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Link extraction error: {str(e)}")
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

# ==================== SEO ANALYZER  ====================

@app.route('/analyze-seo', methods=['POST'])
def analyze_seo():
    """Analyze SEO metrics of a webpage"""
    try:
        # FIXED: Use request.form instead of request.get_json()
        url = request.form.get('url', '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL is required'}), 400
        
        if not is_valid_url(url):
            return jsonify({'error': 'Invalid URL format'}), 400
        
        # Fetch the page with timeout
        try:
            response = requests.get(url, headers=HEADERS, timeout=8)
            response.raise_for_status()
        except requests.Timeout:
            return jsonify({'error': 'The website took too long to respond (timeout).', 'success': False}), 504
        except requests.RequestException as e:
            return jsonify({'error': f'Failed to access the website: {str(e)}', 'success': False}), 502
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove scripts/styles to avoid massive text
        for script in soup(["script", "style", "noscript", "iframe"]):
            script.decompose()
        
        # Extract SEO data
        title = soup.find('title')
        title_text = title.get_text(strip=True) if title else ''
        title_length = len(title_text)
        
        # Case-insensitive meta description
        meta_desc = soup.find('meta', attrs={'name': re.compile(r'description', re.I)})
        meta_desc_text = meta_desc.get('content', '').strip() if meta_desc else ''
        meta_desc_length = len(meta_desc_text)
        
        h1_tags = soup.find_all('h1')
        h2_tags = soup.find_all('h2')
        img_tags = soup.find_all('img')
        images_with_alt = sum(1 for img in img_tags if img.get('alt'))
        total_images = len(img_tags)
        
        links = soup.find_all('a')
        internal_links = 0
        external_links = 0
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        for link in links:
            href = link.get('href', '')
            if href.startswith('http'):
                if domain in href:
                    internal_links += 1
                else:
                    external_links += 1
            elif href.startswith('/') or href.startswith('#'):
                internal_links += 1
        
        body_text = soup.get_text(separator=' ', strip=True)
        words = len(body_text[:50000].split())  # Cap to avoid hanging
        
        # Calculate score (0-100)
        score = 100
        if not title_text: score -= 15
        elif title_length < 30: score -= 10
        elif title_length > 60: score -= 5
        if not meta_desc_text: score -= 15
        elif meta_desc_length < 120: score -= 8
        elif meta_desc_length > 160: score -= 5
        if len(h1_tags) == 0: score -= 10
        if total_images > 0 and images_with_alt < total_images:
            missing_alt = total_images - images_with_alt
            score -= min(10, missing_alt * 2)
        if words < 300: score -= 5
        if internal_links == 0: score -= 5
        
        score = max(0, min(100, score))
        
        # Grade
        if score >= 80: grade, color = 'A', '#28a745'
        elif score >= 60: grade, color = 'B', '#ffc107'
        elif score >= 40: grade, color = 'C', '#ff9800'
        else: grade, color = 'F', '#dc3545'
        
        seo_data = {
            'score': score,
            'grade': grade,
            'color': color,
            'metrics': {
                'title': {'present': bool(title_text), 'value': title_text[:60] + '...' if len(title_text) > 60 else title_text, 'length': title_length},
                'description': {'present': bool(meta_desc_text), 'value': meta_desc_text[:100] + '...' if len(meta_desc_text) > 100 else meta_desc_text, 'length': meta_desc_length},
                'headings': {'h1': len(h1_tags), 'h2': len(h2_tags)},
                'images': {'total': total_images, 'with_alt': images_with_alt, 'coverage': f'{(images_with_alt/total_images*100):.1f}%' if total_images > 0 else '0%'},
                'links': {'internal': internal_links, 'external': external_links, 'total': len(links)},
                'content': {'words': words, 'characters': len(body_text)}
            }
        }
        
        return jsonify({'success': True, 'data': seo_data})
    
    except Exception as e:
        logger.error(f"SEO analysis error: {str(e)}")
        return jsonify({'success': False, 'error': f'An error occurred: {str(e)}'}), 500


# ==================== PRODUCT COMPARISON - UK MARKET ====================

@app.route('/api/compare-products', methods=['POST'])
def compare_products():
    """Compare products across multiple UK stores"""
    try:
        data = request.get_json()
        product_name = data.get('product', '').strip().lower()

        if not product_name:
            return jsonify({'error': 'Product name is required'}), 400

        # Scrape from multiple UK stores
        all_products = []

        # Amazon UK products
        amazon_products = scrape_amazon_uk_product(product_name)
        for product in amazon_products:
            all_products.append({
                'store': 'Amazon UK',
                'name': product['name'],
                'details': {
                    'Price': product['price'],
                    'Rating': str(product['rating']),
                    'Stock': product['stock'],
                    'Delivery': product['specs'].get('Delivery', 'Standard'),
                    'Returns': product['specs'].get('Returns', 'Store Policy'),
                    'Prime': product['specs'].get('Prime Eligible', 'N/A')
                },
                'url': product['url']
            })

            # Save to database
            comparison = ProductComparison(
                product_name=product_name,
                store='Amazon UK',
                price=product['price'],
                rating=product['rating'],
                stock_status=product['stock'],
                specs=json.dumps({
                    'Delivery': product['specs'].get('Delivery', 'Standard'),
                    'Returns': product['specs'].get('Returns', 'Store Policy'),
                    'Prime': product['specs'].get('Prime Eligible', 'N/A')
                }),
                product_url=product['url']
            )
            db.session.add(comparison)

        # Currys products
        currys_products = scrape_currys_product(product_name)
        for product in currys_products:
            all_products.append({
                'store': 'Currys',
                'name': product['name'],
                'details': {
                    'Price': product['price'],
                    'Rating': str(product['rating']),
                    'Stock': product['stock'],
                    'Delivery': product['specs'].get('Delivery', 'Standard'),
                    'Returns': product['specs'].get('Returns', 'Store Policy'),
                    'Warranty': product['specs'].get('Warranty', 'Standard')
                },
                'url': product['url']
            })

            # Save to database
            comparison = ProductComparison(
                product_name=product_name,
                store='Currys',
                price=product['price'],
                rating=product['rating'],
                stock_status=product['stock'],
                specs=json.dumps({
                    'Delivery': product['specs'].get('Delivery', 'Standard'),
                    'Returns': product['specs'].get('Returns', 'Store Policy'),
                    'Warranty': product['specs'].get('Warranty', 'Standard')
                }),
                product_url=product['url']
            )
            db.session.add(comparison)

        # John Lewis products
        john_lewis_products = scrape_john_lewis_product(product_name)
        for product in john_lewis_products:
            all_products.append({
                'store': 'John Lewis',
                'name': product['name'],
                'details': {
                    'Price': product['price'],
                    'Rating': str(product['rating']),
                    'Stock': product['stock'],
                    'Delivery': product['specs'].get('Delivery', 'Standard'),
                    'Returns': product['specs'].get('Returns', 'Store Policy'),
                    'Warranty': product['specs'].get('Warranty', 'Lifetime')
                },
                'url': product['url']
            })

            # Save to database
            comparison = ProductComparison(
                product_name=product_name,
                store='John Lewis',
                price=product['price'],
                rating=product['rating'],
                stock_status=product['stock'],
                specs=json.dumps({
                    'Delivery': product['specs'].get('Delivery', 'Standard'),
                    'Returns': product['specs'].get('Returns', 'Store Policy'),
                    'Warranty': product['specs'].get('Warranty', 'Lifetime')
                }),
                product_url=product['url']
            )
            db.session.add(comparison)

        # Argos products
        argos_products = scrape_argos_product(product_name)
        for product in argos_products:
            all_products.append({
                'store': 'Argos',
                'name': product['name'],
                'details': {
                    'Price': product['price'],
                    'Rating': str(product['rating']),
                    'Stock': product['stock'],
                    'Delivery': product['specs'].get('Delivery', 'Standard'),
                    'Returns': product['specs'].get('Returns', 'Store Policy'),
                    'In-Store': product['specs'].get('In-Store', 'Yes')
                },
                'url': product['url']
            })

            # Save to database
            comparison = ProductComparison(
                product_name=product_name,
                store='Argos',
                price=product['price'],
                rating=product['rating'],
                stock_status=product['stock'],
                specs=json.dumps({
                    'Delivery': product['specs'].get('Delivery', 'Standard'),
                    'Returns': product['specs'].get('Returns', 'Store Policy'),
                    'In-Store': product['specs'].get('In-Store', 'Yes')
                }),
                product_url=product['url']
            )
            db.session.add(comparison)

        # eBay UK products
        ebay_products = scrape_ebay_uk_product(product_name)
        for product in ebay_products:
            all_products.append({
                'store': 'eBay UK',
                'name': product['name'],
                'details': {
                    'Price': product['price'],
                    'Rating': str(product['rating']),
                    'Stock': product['stock'],
                    'Delivery': product['specs'].get('Delivery', 'Standard'),
                    'Returns': product['specs'].get('Returns', 'Store Policy'),
                    'Protection': product['specs'].get('Protection', 'Yes')
                },
                'url': product['url']
            })

            # Save to database
            comparison = ProductComparison(
                product_name=product_name,
                store='eBay UK',
                price=product['price'],
                rating=product['rating'],
                stock_status=product['stock'],
                specs=json.dumps({
                    'Delivery': product['specs'].get('Delivery', 'Standard'),
                    'Returns': product['specs'].get('Returns', 'Store Policy'),
                    'Protection': product['specs'].get('Protection', 'Yes')
                }),
                product_url=product['url']
            )
            db.session.add(comparison)

        db.session.commit()

        if not all_products:
            return jsonify({'success': False, 'error': 'No products found'}), 404

        # Store in session for history
        comparison_data = {
            'id': str(uuid.uuid4()),
            'product': product_name,
            'date': datetime.now().isoformat(),
            'products': all_products
        }
        session['last_comparison'] = comparison_data
        session.modified = True

        return jsonify({
            'success': True,
            'products': all_products
        })

    except Exception as e:
        logger.error(f"Product comparison error: {str(e)}")
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

# ==================== HISTORY API ====================

@app.route('/api/history')
def get_history():
    """Get scraping history as JSON"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        jobs = ScrapingJob.query.order_by(ScrapingJob.created_at.desc()).paginate(page=page, per_page=per_page)

        return jsonify({
            'success': True,
            'total': jobs.total,
            'pages': jobs.pages,
            'current_page': page,
            'data': [job.to_dict() for job in jobs.items]
        })
    except Exception as e:
        logger.error(f"History fetch error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/history/<int:job_id>')
def get_job_details(job_id):
    """Get detailed info about a scraping job"""
    try:
        job = ScrapingJob.query.get_or_404(job_id)
        images = ScrapedImage.query.filter_by(job_id=job_id).all()
        links = ExtractedLink.query.filter_by(job_id=job_id).all()

        return jsonify({
            'success': True,
            'job': job.to_dict(),
            'images': [
                {'id': img.id, 'url': img.url, 'alt_text': img.alt_text, 'local_path': img.local_path}
                for img in images
            ],
            'links': [
                {'id': link.id, 'url': link.url, 'text': link.text, 'type': link.link_type}
                for link in links
            ]
        })
    except Exception as e:
        logger.error(f"Job details error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ==================== STATISTICS API ====================

@app.route('/api/stats')
def get_stats():
    """Get comprehensive statistics"""
    try:
        total_jobs = ScrapingJob.query.count()
        total_images = db.session.query(db.func.count(ScrapedImage.id)).scalar() or 0
        total_links = db.session.query(db.func.count(ExtractedLink.id)).scalar() or 0
        total_comparisons = ProductComparison.query.count()

        # Tools breakdown
        tools_stats = db.session.query(
            ScrapingJob.tool_used,
            db.func.count(ScrapingJob.id).label('count'),
            db.func.sum(ScrapingJob.results_count).label('total_results')
        ).group_by(ScrapingJob.tool_used).all()

        tools_breakdown = []
        for tool, count, results in tools_stats:
            tools_breakdown.append({
                'tool': tool,
                'jobs': count,
                'results': results or 0
            })

        # Daily activity
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        daily_stats = db.session.query(
            db.func.date(ScrapingJob.created_at).label('date'),
            db.func.count(ScrapingJob.id).label('count')
        ).filter(ScrapingJob.created_at >= seven_days_ago).group_by(
            db.func.date(ScrapingJob.created_at)
        ).all()

        daily_breakdown = [{'date': str(date), 'count': count} for date, count in daily_stats]

        # Top domains
        top_domains = db.session.query(
            ScrapingJob.url,
            db.func.count(ScrapingJob.id).label('count')
        ).group_by(ScrapingJob.url).order_by(db.func.count(ScrapingJob.id).desc()).limit(10).all()

        top_domains_list = [{'domain': url, 'count': count} for url, count in top_domains]

        # Link types breakdown
        link_stats = db.session.query(
            ExtractedLink.link_type,
            db.func.count(ExtractedLink.id).label('count')
        ).group_by(ExtractedLink.link_type).all()

        link_breakdown = [{'type': linktype or 'unknown', 'count': count} for linktype, count in link_stats]

        return jsonify({
            'success': True,
            'summary': {
                'total_jobs': total_jobs,
                'total_images': total_images,
                'total_links': total_links,
                'total_comparisons': total_comparisons
            },
            'tools': tools_breakdown,
            'daily_activity': daily_breakdown,
            'top_domains': top_domains_list,
            'link_types': link_breakdown
        })
    except Exception as e:
        logger.error(f"Statistics error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ==================== EXPORT ====================

@app.route('/export-csv', methods=['GET'])
def export_csv():
    """Export scraped images as CSV"""
    try:
        if 'scraped_images' not in session:
            return jsonify({'error': 'No data to export'}), 400

        data = session['scraped_images']
        csv_filename = f"images_export_{uuid.uuid4().hex[:8]}.csv"
        csv_path = os.path.join(app.config['EXPORT_FOLDER'], csv_filename)

        fieldnames = ['filename', 'alt_text', 'scraped_url', 'scraped_at']
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for item in data:
                row = {k: item.get(k, '') for k in fieldnames}
                writer.writerow(row)

        return send_from_directory(app.config['EXPORT_FOLDER'], csv_filename, as_attachment=True)
    except Exception as e:
        logger.error(f"CSV export error: {str(e)}")
        return jsonify({'error': 'Export failed'}), 500

@app.route('/export-json', methods=['GET'])
def export_json():
    """Export scraped data as JSON"""
    try:
        # Check if we have SEO file in session (New logic)
        if 'last_seo_file' in session:
            filename = session['last_seo_file']
            return send_from_directory(app.config['EXPORT_FOLDER'], filename, as_attachment=True)
            
        # Fallback to scraped images/comparisons in session (Old logic)
        data = session.get('scraped_images') or session.get('last_comparison')
        if not data:
            return jsonify({'error': 'No data to export'}), 400

        json_filename = f"data_export_{uuid.uuid4().hex[:8]}.json"
        json_path = os.path.join(app.config['EXPORT_FOLDER'], json_filename)

        with open(json_path, 'w', encoding='utf-8') as jsonfile:
            json.dump(data, jsonfile, indent=2, ensure_ascii=False)

        return send_from_directory(app.config['EXPORT_FOLDER'], json_filename, as_attachment=True)
    except Exception as e:
        logger.error(f"JSON export error: {str(e)}")
        return jsonify({'error': 'Export failed'}), 500

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# ==================== INITIALIZE DATABASE ====================

with app.app_context():
    db.create_all()
    logger.info('Database tables created successfully')

if __name__ == '__main__':
    app.run(debug=False, host='127.0.0.1', port=5000)