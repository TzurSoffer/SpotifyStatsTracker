Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
docker build --no-cache -t spotify-tracker:latest .
# docker build -t spotify-tracker:latest .
docker tag spotify-tracker:latest mepro3/spotify-tracker:latest
Write-Host "Check that everything looks good, once done, type 'exit'"
docker run --rm -it spotify-tracker:latest sh
docker push mepro3/spotify-tracker:latest