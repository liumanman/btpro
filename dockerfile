FROM tiangolo/uwsgi-nginx-flask:flask-python3.5

MAINTAINER Evan Liu <liumanman@gmail.com>

RUN pip install requests

# Add app configuration to Nginx
#COPY nginx.conf /etc/nginx/conf.d/

# Copy sample app
COPY ./templates /app/templates
COPY ./rss.py /app/rss.py
COPY ./uwsgi.ini /app/uwsgi.ini
COPY ./.btpro /tmp/.btpro

RUN cp -r /tmp/.btpro ~/.btpro