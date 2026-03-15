web: gunicorn rinse_backend.wsgi --bind 0.0.0.0:$PORT
release: python manage.py migrate --no-input && python manage.py seed_items
