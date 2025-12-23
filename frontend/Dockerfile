FROM nginx:alpine

# Copy frontend files
COPY index.html /usr/share/nginx/html/

# Configure nginx with proper websocket upgrade handling
RUN printf "map \$http_upgrade \$connection_upgrade {\n\
    default upgrade;\n\
    ''      close;\n\
}\n\
\n\
server {\n\
    listen 80;\n\
\n\
    # Serve static assets\n\
    location / {\n\
        root /usr/share/nginx/html;\n\
        index index.html;\n\
        try_files \$uri \$uri/ /index.html;\n\
    }\n\
\n\
    # Proxy WebSocket traffic to backend\n\
    location /ws/assistant {\n\
        proxy_pass http://backend:8000;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade \$http_upgrade;\n\
        proxy_set_header Connection \$connection_upgrade;\n\
        proxy_set_header Host \$host;\n\
        proxy_read_timeout 86400;\n\
        proxy_send_timeout 86400;\n\
        proxy_buffering off;\n\
    }\n\
}\n" > /etc/nginx/conf.d/default.conf

EXPOSE 80
