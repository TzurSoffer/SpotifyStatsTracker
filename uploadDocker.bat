find . -type d -name "__pycache__" -exec rm -rf {} +
docker build --no-cache -t spotify-tracker:latest .
docker tag spotify-tracker:latest mepro3/spotify-tracker:latest
docker push mepro3/spotify-tracker:latest