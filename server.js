const express = require('express');
const axios = require('axios');
const cheerio = require('cheerio');
const archiver = require('archiver');
const path = require('path');
const { URL } = require('url');

const app = express();

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname)));

// Serve index.html at the root route
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// Helper function to replace domain in URLs
function replaceDomain(originalUrl, newDomain, baseUrl) {
    try {
        const url = new URL(originalUrl, baseUrl);
        url.hostname = newDomain;
        return url.toString();
    } catch (e) {
        return originalUrl;
    }
}

app.post('/download', async (req, res) => {
    try {
        const { url, replacementDomain } = req.body;
        if (!url || !replacementDomain) {
            return res.status(400).json({ error: 'URL and replacement domain are required' });
        }

        // Fetch the webpage
        const response = await axios.get(url);
        const html = response.data;
        const $ = cheerio.load(html);
        const baseUrl = url;

        // Replace all URLs in various attributes
        $('[href]').each((i, elem) => {
            const href = $(elem).attr('href');
            $(elem).attr('href', replaceDomain(href, replacementDomain, baseUrl));
        });

        $('[src]').each((i, elem) => {
            const src = $(elem).attr('src');
            $(elem).attr('src', replaceDomain(src, replacementDomain, baseUrl));
        });

        // Replace URLs in inline styles
        $('[style]').each((i, elem) => {
            let style = $(elem).attr('style');
            style = style.replace(/url\(['"]?(.*?)['"]?\)/g, (match, p1) => {
                return `url('${replaceDomain(p1, replacementDomain, baseUrl)}')`;
            });
            $(elem).attr('style', style);
        });

        // Replace URLs in style tags
        $('style').each((i, elem) => {
            let css = $(elem).html();
            css = css.replace(/url\(['"]?(.*?)['"]?\)/g, (match, p1) => {
                return `url('${replaceDomain(p1, replacementDomain, baseUrl)}')`;
            });
            $(elem).html(css);
        });

        // Create a ZIP archive
        const archive = archiver('zip', {
            zlib: { level: 9 }
        });

        // Set the response headers for ZIP download
        res.attachment('website.zip');
        archive.pipe(res);

        // Add the modified HTML to the ZIP
        archive.append($.html(), { name: 'index.html' });

        // Finalize the archive
        await archive.finalize();

    } catch (error) {
        console.error('Error:', error);
        res.status(500).json({ error: 'Failed to process the website' });
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
    console.log(`Open http://localhost:${PORT} in your browser`);
}); 