Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
docker build --no-cache -t spotify-tracker:nightly .
# docker build -t spotify-tracker:latest .
docker tag spotify-tracker:nightly mepro3/spotify-tracker:nightly
Write-Host "Check that everything looks good, once done, type 'exit'"
docker run --rm -it spotify-tracker:nightly sh
docker push mepro3/spotify-tracker:nightly