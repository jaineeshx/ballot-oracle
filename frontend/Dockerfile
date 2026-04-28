FROM nginx:1.25-alpine

# Copy static assets
COPY index.html  /usr/share/nginx/html/
COPY style.css   /usr/share/nginx/html/
COPY app.js      /usr/share/nginx/html/

# Custom nginx config: gzip, proper MIME types, SPA routing
RUN cat > /etc/nginx/conf.d/default.conf << 'EOF'
server {
    listen 8080;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    gzip on;
    gzip_types text/css application/javascript text/html;
    gzip_min_length 256;

    location / {
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-cache";
    }

    location ~* \.(css|js)$ {
        expires 1d;
        add_header Cache-Control "public";
    }
}
EOF

EXPOSE 8080
