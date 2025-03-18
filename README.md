# Website Scraper

A web application that allows users to download and clone websites with domain replacement functionality.

## Features

- Website cloning with domain replacement
- User-friendly web interface
- Progress tracking and error handling
- Automated deployment via GitHub Actions

## Tech Stack

- Frontend: HTML, CSS, JavaScript
- Backend: Python (Flask) and Node.js
- Deployment: GitHub Pages and GitHub Actions

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/website-scraper.git
cd website-scraper
```

2. Install dependencies:
```bash
# Python dependencies
pip install -r requirements.txt

# Node.js dependencies
npm install
```

3. Run the application:
```bash
# Start the Python backend
python app.py

# Start the Node.js server
node server.js
```

4. Open your browser and navigate to `http://localhost:3000`

## Usage

1. Enter the URL of the website you want to scrape
2. Enter the replacement domain
3. Click "Download Website"
4. Wait for the download to complete

## Development

The project structure is organized as follows:
- `/static` - Static assets (CSS, JavaScript)
- `/templates` - HTML templates
- `app.py` - Python backend server
- `server.js` - Node.js server
- `index.html` - Main application page

## License

MIT License - feel free to use this project for your own purposes.

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request 