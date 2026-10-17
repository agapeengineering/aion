FROM nginxinc/nginx-unprivileged:1.30.1-alpine@sha256:acc3239879a65d9e3d250b21847ec3f34f33367017394d22830242af15cf1cb0
COPY apps/web/dist /usr/share/nginx/html
COPY deploy/web/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
