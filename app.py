from flask import Flask, request, send_file, jsonify, render_template
import os
import requests
from bs4 import BeautifulSoup
import wget
import shutil
from urllib.parse import urljoin, urlparse, urlunparse
import time
import uuid
import re
import json
import mimetypes
import hashlib
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import chardet

app = Flask(__name__)
app.logger.setLevel('INFO')  # Set the logging level

# Function to remove unnecessary scripts from <script> tags
def is_tracking_script(script_content):
    """Checks if the script contains specific tracking or unnecessary backend code."""
    tracking_keywords = ['clickfunnels', 'fb', 'track', 'funnel', 'cf', 'google-analytics']
    return any(keyword in script_content.lower() for keyword in tracking_keywords)

def remove_unnecessary_scripts(soup):
    """Remove unnecessary <script> tags"""
    for script in soup.find_all('script'):
        if script.string and is_tracking_script(script.string):
            script.decompose()  # Remove the script if it matches the tracking patterns

# Function to remove external domains and replace with the original domain
def remove_external_domains(soup, original_domain):
    """Replace all external domains (except the original) with the original domain, preserving trusted CDNs"""
    # List of CDNs to preserve (do not replace)
    preserve_cdns = [
        'fontawesome.com', 'googleapis.com', 'bootstrapcdn.com', 'jquery.com', 'cdnjs.cloudflare.com', 'unpkg.com'
    ]
    
    for tag in soup.find_all(['a', 'img', 'script', 'link']):
        src = tag.get('href') or tag.get('src')
        if src:
            parsed_url = urlparse(src)
            domain = parsed_url.netloc.lower()

            # Skip replacement for trusted CDNs in the preserve list
            if any(preserve_cdn in domain for preserve_cdn in preserve_cdns):
                # If it's from a CDN we want to preserve, keep the original link
                if src.startswith('//'):
                    tag['href'] = 'https:' + src  # Ensure it's HTTPS
                    tag['src'] = 'https:' + src  # Ensure it's HTTPS
                elif not src.startswith(('http://', 'https://')):
                    tag['href'] = urljoin(original_domain, src)
                    tag['src'] = urljoin(original_domain, src)
                continue

            # Replace external domains with the original one
            if parsed_url.netloc and parsed_url.netloc != original_domain:
                new_url = src.replace(parsed_url.netloc, original_domain)
                if tag.get('href'):
                    tag['href'] = new_url
                if tag.get('src'):
                    tag['src'] = new_url




def get_file_extension(url, content_type=None):
    """Get file extension from URL or content type"""
    # Try to get extension from URL first
    ext = os.path.splitext(urlparse(url).path)[1]
    if ext:
        return ext.lower()

    # If no extension in URL, try to get from content type
    if content_type:
        ext = mimetypes.guess_extension(content_type)
        if ext:
            return ext.lower()

    # Default extensions based on content type patterns
    if content_type:
        if 'image' in content_type:
            return '.jpg'
        if 'video' in content_type:
            return '.mp4'
        if 'javascript' in content_type:
            return '.js'
        if 'css' in content_type:
            return '.css'
        if 'font' in content_type:
            return '.woff2'
    
    return '.bin'  # Default extension if nothing else works

def safe_filename(url):
    """Convert URL to a safe filename"""
    # Get the last part of the URL (filename)
    filename = os.path.basename(urlparse(url).path)
    if not filename:
        filename = 'index'
    
    # Remove query parameters if present
    filename = filename.split('?')[0]
    
    # Replace unsafe characters
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    
    # Ensure the filename isn't empty
    if not filename:
        filename = 'unnamed'
        
    return filename

def safe_download(url, save_path):
    try:
        # Ensure the URL is valid
        parsed_url = urlparse(url)
        if not parsed_url.scheme:
            url = 'https://' + url
        if not parsed_url.scheme and not parsed_url.netloc:
            return None

        # Download with timeout and proper headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, stream=True, timeout=(10, 30), headers=headers, allow_redirects=True)
        response.raise_for_status()

        # Get content type and extension
        content_type = response.headers.get('Content-Type', '').split(';')[0]
        ext = get_file_extension(url, content_type)

        # Create unique filename using hash of URL
        url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
        filename = f"{url_hash}{ext}"
        full_path = os.path.join(save_path, filename)

        # Save file with proper encoding to handle unicode characters
        with open(full_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return filename
    except Exception as e:
        print(f'Error downloading {url}: {str(e)}')
        return None

def replace_domain_in_url(url, original_domains, new_domains, base_url):
    try:
        # Handle relative URLs and decode URL-encoded characters
        full_url = urljoin(base_url, url)
        parsed = urlparse(full_url)
        
        # Skip if it's a relative URL without domain
        if not parsed.netloc:
            return url
            
        # Remove www. from current domain
        current_domain = parsed.netloc.replace('www.', '')
        
        # Try each domain pair for replacement
        for orig_domain, new_domain in zip(original_domains, new_domains):
            # Remove www. from domains for comparison
            orig_domain = orig_domain.strip().lower().replace('www.', '')
            new_domain = new_domain.strip().lower().replace('www.', '')
            
            # Only replace if it matches the original domain
            if current_domain == orig_domain:
                # Create new URL with replaced domain, preserving the path encoding
                new_url = full_url.replace(parsed.netloc, new_domain)
                return new_url
    except:
        pass
    return url

def replace_text_content(text, original_domains, replacement_domains):
    if not text:
        return text
    
    # Process each domain pair
    for orig_domain, repl_domain in zip(original_domains, replacement_domains):
        orig_domain = orig_domain.strip().lower()
        repl_domain = repl_domain.strip().lower()
        
        # Replace both www and non-www versions
        text = text.replace(f'www.{orig_domain}', repl_domain)
        text = text.replace(orig_domain, repl_domain)
        
        # Replace encoded versions (for JavaScript/JSON content)
        text = text.replace(f'\\"{orig_domain}\\"', f'\\"{repl_domain}\\"')
        text = text.replace(f"\\'{orig_domain}\\'", f"\\'{repl_domain}\\'")
        
        # Replace URL-encoded versions
        text = text.replace(f'%22{orig_domain}%22', f'%22{repl_domain}%22')
    
    return text

def download_and_save_asset(url, base_url, save_path, asset_type):
    """Download and save an asset, checking for HTTPS calls in JavaScript files"""
    try:
        # Handle relative URLs
        if url.startswith('//'):
            url = 'https:' + url
        elif url.startswith('/'):
            url = urljoin(base_url, url)
        elif not url.startswith(('http://', 'https://')):
            url = urljoin(base_url, url)

        # Skip if already downloaded
        if os.path.exists(save_path):
            return True

        # Download the asset
        response = requests.get(url, stream=True, timeout=10)
        response.raise_for_status()

        # For JavaScript files, check for HTTPS calls
        if asset_type == 'js':
            content = response.text
            if 'https' in content.lower():
                print(f"Removing script with HTTPS calls: {url}")
                return False

        # Save the asset
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True

    except Exception as e:
        print(f"Error downloading {url}: {str(e)}")
        return False

def contains_https_calls(content):
    """Check if content contains HTTPS calls"""
    if not content:
        return False
    
    # Patterns for HTTPS calls
    patterns = [
        r'https?://[^\s<>"]+',  # URLs
        r'fetch\([\'"](https?://[^\'"]+)[\'"]',  # Fetch calls
        r'XMLHttpRequest\([\'"](https?://[^\'"]+)[\'"]',  # XHR calls
        r'axios\.(get|post|put|delete)\([\'"](https?://[^\'"]+)[\'"]',  # Axios calls
        r'\.ajax\([\'"](https?://[^\'"]+)[\'"]',  # jQuery AJAX calls
        r'new Image\([\'"](https?://[^\'"]+)[\'"]',  # Image loading
        r'\.src\s*=\s*[\'"](https?://[^\'"]+)[\'"]',  # Source assignments
        r'\.href\s*=\s*[\'"](https?://[^\'"]+)[\'"]',  # Href assignments
        r'\.setAttribute\([\'"]src[\'"],\s*[\'"](https?://[^\'"]+)[\'"]',  # setAttribute calls
        r'\.setAttribute\([\'"]href[\'"],\s*[\'"](https?://[^\'"]+)[\'"]',
        r'\.load\([\'"](https?://[^\'"]+)[\'"]',  # jQuery load
        r'\.get\([\'"](https?://[^\'"]+)[\'"]',  # jQuery get
        r'\.post\([\'"](https?://[^\'"]+)[\'"]',  # jQuery post
        r'\.getScript\([\'"](https?://[^\'"]+)[\'"]',  # jQuery getScript
        r'\.getJSON\([\'"](https?://[^\'"]+)[\'"]',  # jQuery getJSON
        r'\.animate\([\'"](https?://[^\'"]+)[\'"]',  # jQuery animate
        r'\.replace\([\'"](https?://[^\'"]+)[\'"]',  # String replace with URL
        r'\.assign\([\'"](https?://[^\'"]+)[\'"]',  # Window location assign
        r'\.replace\([\'"](https?://[^\'"]+)[\'"]',  # Window location replace
        r'\.open\([\'"](https?://[^\'"]+)[\'"]',  # Window open
        r'\.createElement\([\'"]script[\'"]\)',  # Dynamic script creation
        r'\.appendChild\([^)]+\)',  # appendChild with potential script
        r'\.insertBefore\([^)]+\)',  # insertBefore with potential script
        r'eval\([^)]+\)',  # eval calls
        r'new Function\([^)]+\)',  # Function constructor
        r'\.importScripts\([^)]+\)',  # importScripts
        r'\.import\([^)]+\)',  # dynamic imports
        r'require\([^)]+\)',  # require calls
        r'import\s+[^;]+from\s+[\'"][^\'"]+[\'"]'  # ES6 imports
    ]
    
    return any(re.search(pattern, content, re.IGNORECASE) for pattern in patterns)

def download_and_replace_image(img_url, save_dir, base_url):
    """Download image and return local path"""
    try:
        if not img_url.startswith(('http://', 'https://')):
            img_url = urljoin(base_url, img_url)
        
        # Create images directory if it doesn't exist
        img_dir = os.path.join(save_dir, 'images')
        os.makedirs(img_dir, exist_ok=True)
        
        # Generate safe filename
        filename = safe_filename(img_url)
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.ico', '.webp')):
            filename += '.png'  # Default to PNG if no extension
        
        local_path = os.path.join('images', filename)
        full_path = os.path.join(save_dir, local_path)
        
        # Download the image
        response = requests.get(img_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }, stream=True)
        
        if response.ok:
            with open(full_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return local_path
        return None
    except Exception as e:
        print(f"Error downloading image {img_url}: {str(e)}")
        return None

def remove_tracking_scripts(soup, remove_tracking=True, remove_custom_tracking=True, remove_redirects=False, save_dir=None, base_url=None):
    """Remove various tracking scripts from the HTML"""
    if not (remove_tracking or remove_custom_tracking or remove_redirects):
        return

    # List of trusted CDNs
    trusted_cdns = [
        'cdnjs.cloudflare.com',
        'unpkg.com',
        'jsdelivr.net',
        'bootstrapcdn.com',
        'jquery.com',
        'bootstrap.com',
        'fontawesome.com',
        'googleapis.com',
        'microsoft.com',
        'cloudflare.com',
        'amazonaws.com',
        'cloudfront.net'
    ]

    def is_trusted_cdn(url):
        """Check if URL is from a trusted CDN"""
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()
        return any(cdn in domain for cdn in trusted_cdns)

    # Common tracking script patterns
    tracking_patterns = [
        # Meta Pixel
        r'connect\.facebook\.net/[^/]+/fbevents\.js',
        r'facebook-jssdk',
        r'fb-root',
        # Google Analytics
        r'google-analytics\.com/analytics\.js',
        r'googletagmanager\.com/gtag/js',
        r'ga\.js',
        r'gtag',
        # Google Tag Manager
        r'googletagmanager\.com/gtm\.js',
        r'gtm\.js',
        # Ringba
        r'ringba\.com',
        r'ringba\.js',
        # Other common trackers
        r'analytics',
        r'pixel\.js',
        r'tracking\.js',
        r'mixpanel',
        r'segment\.com',
        r'hotjar\.com',
    ]

    # Custom track.js patterns
    custom_tracking_patterns = [
        r'track\.js',
        r'tracking\.js',
        r'tracker\.js',
    ]

    def matches_patterns(src, patterns):
        if not src:
            return False
        return any(re.search(pattern, src, re.IGNORECASE) for pattern in patterns)

    # Handle favicon and header images first
    if save_dir and base_url:
        for link in soup.find_all('link', rel=['icon', 'shortcut icon', 'apple-touch-icon']):
            href = link.get('href')
            if href and href.startswith(('http://', 'https://')):
                local_path = download_and_replace_image(href, save_dir, base_url)
                if local_path:
                    link['href'] = local_path

    # Remove script tags
    for script in soup.find_all('script'):
        src = script.get('src', '')
        content = script.string or ''
        
        should_remove = False
        
        # Check for tracking patterns
        if remove_tracking:
            should_remove = should_remove or matches_patterns(src, tracking_patterns)
            should_remove = should_remove or any(p in content.lower() for p in ['fbq(', 'gtag(', 'ga(', '_ringba', 'mixpanel'])
            
        if remove_custom_tracking:
            should_remove = should_remove or matches_patterns(src, custom_tracking_patterns)
            should_remove = should_remove or 'track' in content.lower()
        
        # Check for HTTPS calls in external scripts
        if src and src.startswith('http'):
            if not is_trusted_cdn(src):
                should_remove = True
        
        # Check for HTTPS calls in inline scripts
        if content and contains_https_calls(content):
            should_remove = True
        
        if should_remove:
            script.decompose()

    # Remove meta tags related to tracking
    if remove_tracking:
        for meta in soup.find_all('meta'):
            if meta.get('name') in ['facebook-domain-verification', 'google-site-verification']:
                meta.decompose()

    # Remove noscript tags that might contain tracking pixels
    for noscript in soup.find_all('noscript'):
        content = str(noscript).lower()
        if any(tracker in content for tracker in ['facebook', 'gtm', 'google-analytics']):
            noscript.decompose()

    # Remove inline tracking scripts from onclick and other event handlers
    for element in soup.find_all(True):
        for attr in list(element.attrs):
            if attr.startswith('on'):
                value = element[attr].lower()
                if 'track' in value or any(tracker in value for tracker in ['gtag', 'ga', 'fbq']):
                    del element[attr]

    # Remove links that redirect to external sites
    if remove_redirects:
        for link in soup.find_all('a', href=True):
            href = link['href']
            if urlparse(href).netloc and urlparse(href).netloc != urlparse(base_url).netloc:
                link.decompose()  # Remove the link if it redirects to an external site

    # Remove script tags that redirect to external sites
    if remove_redirects:
        for script in soup.find_all('script'):
            src = script.get('src', '')
            if src and urlparse(src).netloc and urlparse(src).netloc != urlparse(base_url).netloc:
                script.decompose()  # Remove the script if it redirects to an external site

def detect_encoding(content):
    """Detects the correct encoding of a webpage."""
    # First try to detect encoding from the content
    detected = chardet.detect(content)
    encoding = detected.get("encoding", "utf-8")
    
    # If confidence is low, try to find encoding in meta tags
    if detected.get("confidence", 0) < 0.8:
        soup = BeautifulSoup(content, 'html.parser')
        meta_charset = soup.find('meta', charset=True)
        if meta_charset:
            return meta_charset['charset']
        
        # Look for content-type meta tag
        meta_content_type = soup.find('meta', attrs={'http-equiv': 'Content-Type'})
        if meta_content_type and 'charset=' in meta_content_type.get('content', ''):
            return meta_content_type['content'].split('charset=')[-1]
    
    return encoding

def download_assets(soup, base_url, save_dir):
    """Download all assets and update their references in the HTML"""
    # List of CDNs to keep as HTTPS
    trusted_cdns = [
        'cdnjs.cloudflare.com',
        'unpkg.com',
        'jsdelivr.net',
        'fontawesome.com',
        'bootstrapcdn.com',
        'bootstrap.com',
        'jquery.com',
        'googleapis.com',
    ]

    # Function to check if the URL is from a trusted CDN
    def is_trusted_cdn(url):
        if not url:
            return False
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()
        return any(cdn in domain for cdn in trusted_cdns)

    # Function to check if the link is from specific CDNs we want to preserve
    def should_preserve_cdn(url):
        if not url:
            return False
        preserve_patterns = ['fontawesome.com', 'bootstrap.com', 'bootstrapcdn.com', 'jquery.com']
        return any(pattern in url.lower() for pattern in preserve_patterns)

    # Create asset directories
    for asset_type in ['css', 'js', 'images']:
        os.makedirs(os.path.join(save_dir, asset_type), exist_ok=True)

    # Download CSS files
    for link in soup.find_all('link', rel='stylesheet'):
        href = link.get('href')
        if href:
            # If it's from a CDN we want to preserve, keep the original link
            if should_preserve_cdn(href):
                # Make sure it's an absolute URL
                if href.startswith('//'):
                    link['href'] = 'https:' + href
                elif not href.startswith(('http://', 'https://')):
                    link['href'] = urljoin(base_url, href)
                # Otherwise keep the original URL
                app.logger.info(f"Preserving CDN CSS: {href}")
            # If it's from another trusted CDN, also keep it
            elif is_trusted_cdn(href):
                # Make sure it's an absolute URL
                if href.startswith('//'):
                    link['href'] = 'https:' + href
                elif not href.startswith(('http://', 'https://')):
                    link['href'] = urljoin(base_url, href)
                app.logger.info(f"Keeping trusted CDN CSS: {href}")
            else:
                # Otherwise, download locally and update the href
                filename = safe_filename(href)
                save_path = os.path.join(save_dir, 'css', filename)
                if download_and_save_asset(href, base_url, save_path, 'css'):
                    link['href'] = f'css/{filename}'
                    app.logger.info(f"Downloaded CSS locally: {href} -> css/{filename}")

    # Download JavaScript files
    for script in soup.find_all('script', src=True):
        src = script.get('src')
        if src:
            # If it's from a CDN we want to preserve, keep the original link
            if should_preserve_cdn(src):
                # Make sure it's an absolute URL
                if src.startswith('//'):
                    script['src'] = 'https:' + src
                elif not src.startswith(('http://', 'https://')):
                    script['src'] = urljoin(base_url, src)
                # Otherwise keep the original URL
                app.logger.info(f"Preserving CDN JS: {src}")
            # If it's from another trusted CDN, also keep it
            elif is_trusted_cdn(src):
                # Make sure it's an absolute URL
                if src.startswith('//'):
                    script['src'] = 'https:' + src
                elif not src.startswith(('http://', 'https://')):
                    script['src'] = urljoin(base_url, src)
                app.logger.info(f"Keeping trusted CDN JS: {src}")
            else:
                # Otherwise, download locally and update the src
                filename = safe_filename(src)
                save_path = os.path.join(save_dir, 'js', filename)
                if download_and_save_asset(src, base_url, save_path, 'js'):
                    script['src'] = f'js/{filename}'
                    app.logger.info(f"Downloaded JS locally: {src} -> js/{filename}")
                else:
                    script.decompose()  # Remove the script if HTTPS call is detected
                    app.logger.info(f"Removed JS with HTTPS calls: {src}")

    # Download images
    for img in soup.find_all('img'):
        src = img.get('src')
        if src:
            # If it's from a CDN we want to preserve, keep the original link
            if should_preserve_cdn(src) or is_trusted_cdn(src):
                # Make sure it's an absolute URL
                if src.startswith('//'):
                    img['src'] = 'https:' + src
                elif not src.startswith(('http://', 'https://')):
                    img['src'] = urljoin(base_url, src)
                # Otherwise keep the original URL
            else:
                # Otherwise, download locally and update the src
                filename = safe_filename(src)
                save_path = os.path.join(save_dir, 'images', filename)
                if download_and_save_asset(src, base_url, save_path, 'images'):
                    img['src'] = f'images/{filename}'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
@app.route('/download', methods=['POST'])
def download_website():
    try:
        # Step 1: Get the input data from the request
        data = request.json
        app.logger.error('Received data: %s', data)
        if not data:
            app.logger.error('Invalid JSON data')
            return jsonify({'error': 'Invalid JSON data'}), 400

        url = data.get('url')
        app.logger.info('URL provided: %s', url)
        if not url:
            app.logger.error('URL is required')
            return jsonify({'error': 'URL is required'}), 400

        # Handle optional domain replacement
        original_domains = [d.strip() for d in data.get('originalDomain', '').split(',') if d.strip()]
        replacement_domains = [d.strip() for d in data.get('replacementDomain', '').split(',') if d.strip()]
        app.logger.info('Original domains: %s', original_domains)
        app.logger.info('Replacement domains: %s', replacement_domains)
        
        # Get optional tracking removal settings
        remove_tracking = data.get('removeTracking', False)
        remove_custom_tracking = data.get('removeCustomTracking', False)
        remove_redirects = data.get('removeRedirects', False)
        app.logger.info('Remove tracking: %s, Remove custom tracking: %s, Remove redirects: %s', remove_tracking, remove_custom_tracking, remove_redirects)
        
        # Validate domains if they are provided
        if original_domains or replacement_domains:
            if not original_domains:
                app.logger.error('Original domains are required when using domain replacement')
                return jsonify({'error': 'Original domains are required when using domain replacement'}), 400
            if not replacement_domains:
                app.logger.error('Replacement domains are required when using domain replacement')
                return jsonify({'error': 'Replacement domains are required when using domain replacement'}), 400
            if len(original_domains) != len(replacement_domains):
                app.logger.error('Number of original domains must match number of replacement domains')
                return jsonify({'error': 'Number of original domains must match number of replacement domains'}), 400
            
            # Clean up domain inputs
            original_domains = [d.strip().lower().replace('www.', '') for d in original_domains]
            replacement_domains = [d.strip().lower().replace('www.', '') for d in replacement_domains]
            app.logger.info('Cleaned original domains: %s', original_domains)
            app.logger.info('Cleaned replacement domains: %s', replacement_domains)

        # Step 2: Download the webpage content
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        response.raise_for_status()
        
        # Step 3: Create save directory
        save_dir = f'temp_website_{int(time.time())}'
        os.makedirs(save_dir, exist_ok=True)
        
        # Step 4: Detect encoding and create soup object
        encoding = detect_encoding(response.content)
        html_content = response.content.decode(encoding)
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Step 5: Remove tracking scripts if requested
        if remove_tracking or remove_custom_tracking or remove_redirects:
            remove_tracking_scripts(soup, remove_tracking, remove_custom_tracking, remove_redirects, save_dir, url)

        # Step 6: Remove unnecessary scripts and external domains (preserving trusted CDNs)
        remove_unnecessary_scripts(soup)  # Remove scripts related to tracking or back-end funnels
        remove_external_domains(soup, urlparse(url).netloc)  # Replace external domains with the original domain
        
        # Step 7: Download assets (CSS, JS, images) and get modified soup
        download_assets(soup, url, save_dir)
        
        # Step 8: Save the final HTML
        with open(os.path.join(save_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))
        
        # Step 9: Create zip file
        zip_name = f'website_{int(time.time())}.zip'
        shutil.make_archive(os.path.splitext(zip_name)[0], 'zip', save_dir)
        
        # Step 10: Clean up the temporary directory
        try:
            shutil.rmtree(save_dir)
        except Exception as e:
            app.logger.error('Error cleaning up temporary directory: %s', str(e))
        
        # Step 11: Send the zip file
        if os.path.exists(zip_name):
            response = send_file(zip_name, as_attachment=True, mimetype='application/zip')
            # Clean up zip file after sending
            try:
                os.remove(zip_name)
                app.logger.info('Zip file removed after sending')
            except Exception as e:
                app.logger.error('Error removing zip file: %s', str(e))
            return response
        else:
            app.logger.error('Error: Zip file not created')
            return jsonify({'error': 'Failed to create zip file'}), 500
    except Exception as e:
        app.logger.error('Exception occurred: %s', str(e))
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)
