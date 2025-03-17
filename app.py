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

app = Flask(__name__)

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

        # Save file
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

def download_and_save_asset(url, base_url, save_dir, asset_type):
    """Download asset and return local path"""
    try:
        # Handle URL-encoded paths and make URL absolute
        full_url = urljoin(base_url, url.strip())
        if not urlparse(full_url).scheme:
            full_url = 'https://' + full_url

        asset_dir = os.path.join(save_dir, asset_type)
        filename = safe_download(full_url, asset_dir)
        if filename:
            return f'{asset_type}/{filename}'
    except Exception as e:
        print(f'Error downloading asset {url}: {str(e)}')
    return url  # Return original URL if download fails

def remove_tracking_scripts(soup, remove_tracking=True, remove_custom_tracking=True):
    """Remove various tracking scripts from the HTML"""
    if not (remove_tracking or remove_custom_tracking):
        return

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

    # Remove script tags
    for script in soup.find_all('script'):
        src = script.get('src', '')
        content = script.string or ''
        
        should_remove = False
        
        if remove_tracking:
            should_remove = should_remove or matches_patterns(src, tracking_patterns)
            should_remove = should_remove or any(p in content.lower() for p in ['fbq(', 'gtag(', 'ga(', '_ringba', 'mixpanel'])
            
        if remove_custom_tracking:
            should_remove = should_remove or matches_patterns(src, custom_tracking_patterns)
            should_remove = should_remove or 'track' in content.lower()
        
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

def download_assets(url, original_domains=None, replacement_domains=None, save_dir=None, remove_tracking=False, remove_custom_tracking=False):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Create save directory if it doesn't exist
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # Step 1: Download the HTML content first
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Check content type to ensure we're getting HTML
        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
            return "Error: URL does not return HTML content"

        html_content = response.text
        base_url = url
        soup = BeautifulSoup(html_content, 'html.parser')

        # Ensure we have a head section
        if not soup.head:
            head = soup.new_tag('head')
            if soup.html:
                soup.html.insert(0, head)
            else:
                html = soup.new_tag('html')
                html.append(head)
                soup.append(html)

        # Create directories for different asset types
        asset_types = {
            'images': ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'],
            'css': ['.css'],
            'js': ['.js'],
            'videos': ['.mp4', '.webm', '.ogg'],
            'fonts': ['.woff', '.woff2', '.ttf', '.eot', '.otf'],
            'icons': ['.ico', '.png'],
            'others': []
        }
        
        for asset_type in asset_types:
            os.makedirs(os.path.join(save_dir, asset_type), exist_ok=True)

        # Dictionary to store downloaded files and their local paths
        downloaded_files = {}

        # Step 2: First download all assets
        def download_all_assets():
            # Process all elements with URL attributes
            url_attributes = {
                'img': ['src', 'data-src'],
                'script': ['src'],
                'link': ['href'],
                'video': ['src', 'poster'],
                'source': ['src'],
                'audio': ['src'],
                'iframe': ['src'],
                'embed': ['src'],
                'object': ['data'],
                'input': ['src'],
                'meta': ['content']
            }

            for tag, attrs in url_attributes.items():
                for element in soup.find_all(tag):
                    for attr in attrs:
                        if element.has_attr(attr):
                            original_url = element[attr]
                            if original_url.startswith('data:'):
                                continue
                                
                            try:
                                # Make URL absolute
                                absolute_url = urljoin(base_url, original_url)
                                
                                # Skip if already downloaded
                                if absolute_url in downloaded_files:
                                    element[attr] = downloaded_files[absolute_url]
                                    continue

                                # Determine asset type and download
                                ext = os.path.splitext(urlparse(absolute_url).path)[1].lower()
                                asset_type = 'others'
                                for type_name, extensions in asset_types.items():
                                    if ext in extensions:
                                        asset_type = type_name
                                        break

                                local_path = download_and_save_asset(absolute_url, base_url, save_dir, asset_type)
                                if local_path:
                                    downloaded_files[absolute_url] = local_path
                                    element[attr] = local_path
                            except Exception as e:
                                print(f'Error processing URL {original_url}: {str(e)}')

            # Download and process CSS files
            for link in soup.find_all('link', rel='stylesheet'):
                if link.get('href'):
                    try:
                        css_url = urljoin(base_url, link['href'])
                        if css_url in downloaded_files:
                            link['href'] = downloaded_files[css_url]
                            continue

                        css_response = requests.get(css_url, headers=headers)
                        if css_response.ok:
                            css_content = css_response.text
                            
                            # Download assets referenced in CSS
                            url_pattern = r'url\([\'"]?((?!data:)[^\'"\)]+)[\'"]?\)'
                            for match in re.finditer(url_pattern, css_content):
                                css_asset_url = match.group(1)
                                if not css_asset_url.startswith('data:'):
                                    absolute_url = urljoin(css_url, css_asset_url)
                                    if absolute_url not in downloaded_files:
                                        # Determine asset type
                                        ext = os.path.splitext(urlparse(absolute_url).path)[1].lower()
                                        asset_type = 'others'
                                        for type_name, extensions in asset_types.items():
                                            if ext in extensions:
                                                asset_type = type_name
                                                break
                                        
                                        local_path = download_and_save_asset(absolute_url, base_url, save_dir, asset_type)
                                        if local_path:
                                            downloaded_files[absolute_url] = local_path
                                            css_content = css_content.replace(css_asset_url, f'../{local_path}')

                            # Save processed CSS
                            css_filename = f"style_{hashlib.md5(css_url.encode()).hexdigest()[:10]}.css"
                            css_path = os.path.join(save_dir, 'css', css_filename)
                            with open(css_path, 'w', encoding='utf-8') as f:
                                f.write(css_content)
                            
                            downloaded_files[css_url] = f'css/{css_filename}'
                            link['href'] = f'css/{css_filename}'
                    except Exception as e:
                        print(f'Error processing CSS file: {str(e)}')

            # Download JavaScript files
            for script in soup.find_all('script', src=True):
                if script.get('src'):
                    try:
                        js_url = urljoin(base_url, script['src'])
                        if js_url in downloaded_files:
                            script['src'] = downloaded_files[js_url]
                            continue

                        js_response = requests.get(js_url, headers=headers)
                        if js_response.ok:
                            js_content = js_response.text
                            
                            # Save JavaScript file
                            js_filename = f"script_{hashlib.md5(js_url.encode()).hexdigest()[:10]}.js"
                            js_path = os.path.join(save_dir, 'js', js_filename)
                            with open(js_path, 'w', encoding='utf-8') as f:
                                f.write(js_content)
                            
                            downloaded_files[js_url] = f'js/{js_filename}'
                            script['src'] = f'js/{js_filename}'
                    except Exception as e:
                        print(f'Error processing JavaScript file: {str(e)}')

        # Step 3: Download all assets first
        download_all_assets()

        # Step 4: Now perform domain replacements if needed
        if original_domains and replacement_domains:
            # Replace domains in HTML content
            html_content = str(soup)
            html_content = replace_text_content(html_content, original_domains, replacement_domains)
            soup = BeautifulSoup(html_content, 'html.parser')

            # Replace domains in all downloaded JavaScript files
            for js_file in os.listdir(os.path.join(save_dir, 'js')):
                js_path = os.path.join(save_dir, 'js', js_file)
                try:
                    with open(js_path, 'r', encoding='utf-8') as f:
                        js_content = f.read()
                    js_content = replace_text_content(js_content, original_domains, replacement_domains)
                    with open(js_path, 'w', encoding='utf-8') as f:
                        f.write(js_content)
                except Exception as e:
                    print(f'Error processing JavaScript file {js_file}: {str(e)}')

            # Replace domains in all downloaded CSS files
            for css_file in os.listdir(os.path.join(save_dir, 'css')):
                css_path = os.path.join(save_dir, 'css', css_file)
                try:
                    with open(css_path, 'r', encoding='utf-8') as f:
                        css_content = f.read()
                    css_content = replace_text_content(css_content, original_domains, replacement_domains)
                    with open(css_path, 'w', encoding='utf-8') as f:
                        f.write(css_content)
                except Exception as e:
                    print(f'Error processing CSS file {css_file}: {str(e)}')

        # Step 5: Remove tracking scripts if requested
        if remove_tracking or remove_custom_tracking:
            remove_tracking_scripts(soup, remove_tracking, remove_custom_tracking)

        # Save the final modified HTML file
        with open(os.path.join(save_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))

        # Create zip file
        zip_name = f'website_{int(time.time())}.zip'
        shutil.make_archive(os.path.splitext(zip_name)[0], 'zip', save_dir)

        # Clean up the temporary directory
        try:
            shutil.rmtree(save_dir)
        except Exception as e:
            print(f'Error cleaning up temporary directory: {str(e)}')

        return zip_name
    except requests.RequestException as e:
        return f"Error accessing the website: {str(e)}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download_website():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400

        url = data.get('url')
        if not url:
            return jsonify({'error': 'URL is required'}), 400

        # Handle optional domain replacement
        original_domains = [d.strip() for d in data.get('originalDomain', '').split(',') if d.strip()]
        replacement_domains = [d.strip() for d in data.get('replacementDomain', '').split(',') if d.strip()]
        
        # Get optional tracking removal settings
        remove_tracking = data.get('removeTracking', False)
        remove_custom_tracking = data.get('removeCustomTracking', False)
        
        # Validate domains if they are provided
        if original_domains or replacement_domains:
            if not original_domains:
                return jsonify({'error': 'Original domains are required when using domain replacement'}), 400
            if not replacement_domains:
                return jsonify({'error': 'Replacement domains are required when using domain replacement'}), 400
            if len(original_domains) != len(replacement_domains):
                return jsonify({'error': 'Number of original domains must match number of replacement domains'}), 400
            
            # Clean up domain inputs
            original_domains = [d.strip().lower().replace('www.', '') for d in original_domains]
            replacement_domains = [d.strip().lower().replace('www.', '') for d in replacement_domains]
        
        save_dir = f'temp_website_{int(time.time())}'
        zip_file = download_assets(
            url=url,
            original_domains=original_domains,
            replacement_domains=replacement_domains,
            save_dir=save_dir,
            remove_tracking=remove_tracking,
            remove_custom_tracking=remove_custom_tracking
        )
        
        if zip_file.endswith('.zip'):
            response = send_file(zip_file, as_attachment=True, mimetype='application/zip')
            # Clean up zip file after sending
            try:
                os.remove(zip_file)
            except Exception:
                pass
            return response
        else:
            return jsonify({'error': zip_file}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
