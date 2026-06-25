<img width="1418" height="1258" alt="image" src="https://github.com/user-attachments/assets/a372d4d5-0477-4923-9104-4b416f616d14" />

<img width="1418" height="1215" alt="image" src="https://github.com/user-attachments/assets/7bb224a5-098a-4c76-96b2-0e3b43744fed" /> <img width="1412" height="1268" alt="image" src="https://github.com/user-attachments/assets/ed354656-37b5-49e5-a5ca-7a17d5752390" />




# Spotify Stats Tracker
### If you found [this repository](https://github.com/TzurSoffer/SpotifyStatsTracker) useful, please give it a ⭐!.
A web application that allows users to track and analyze their Spotify listening habits and statistics **without Spotify Premium**.

## Features

- View your top songs.
- View your top artists.
- See your listening history.
- Track your spotify recently listened in real time
- Import Spotify data export
- Import musicolet pro exports
- Automatically import files in the 'auto-import folder' with optional filtering

## Installation

1. Clone the repository:
```bash
git clone https://github.com/TzurSoffer/SpotifyStatsTracker
cd SpotifyStatsTracker
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Run the Application

### Using Docker

Use this docker-compose command:
```docker
version: '3.8'

services:
  spotify-tracker:
    image: mepro3/spotify-tracker
    ports:
      - "5000:5000"
    volumes:
      - ./Database:/app/Database/Users
      - ./secrets:/app/secrets
      - ./autoImport:/app/autoImport  #< files put in this folder will be imported automatically
    environment:
      - FLASK_APP=app.py
      - PYTHONUNBUFFERED=1
      - TZ=America/Los_Angeles        #< don't forget to change this or you will get the wrong times for songs
      # - IMPORT_KEYWORD=Weekly       #< Uncomment to apply a filter to what files get auto-imported (only files containing this will be imported)
      # - FLASK_DEBUG=1               #< To get more detailed logs from Flask (provide this when opening an issue)
    restart: always
```

Then you can run `docker compose up -d` and the app should start on `http://127.0.0.1:5000` or `http://yourIp:5000`

### Local Development

1. Start the app:
```bash
python app.py
```

2. Open the app in your browser:
```text
http://127.0.0.1:5000
```
or whatever your IP is

3. Open the app in your browser:
```text
http://127.0.0.1:5000
```

**Note:** The Docker container persists data in the `Database/` directory on your host machine.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please open an issue on the GitHub repository or contact me.
