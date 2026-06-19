import HTML from './index.html';

const ROBOTS = `User-agent: *
Allow: /

Sitemap: https://brickforge.dev/sitemap.xml`;

const SITEMAP = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://brickforge.dev/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>`;

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === '/robots.txt') {
      return new Response(ROBOTS, {
        headers: { 'Content-Type': 'text/plain' },
      });
    }

    if (url.pathname === '/sitemap.xml') {
      return new Response(SITEMAP, {
        headers: { 'Content-Type': 'application/xml' },
      });
    }

    return new Response(HTML, {
      headers: { 'Content-Type': 'text/html;charset=UTF-8' },
    });
  },
};
