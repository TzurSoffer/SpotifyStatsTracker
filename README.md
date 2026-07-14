<img width="1440" height="1222" alt="image" src="https://github.com/user-attachments/assets/3720b7f0-1f3d-480d-8fc8-3a9abb73aa90" />
<img width="1434" height="1113" alt="image" src="https://github.com/user-attachments/assets/e65989ce-81d8-48e6-9888-7962993de7c4" />



<img width="1435" height="1264" alt="image" src="https://github.com/user-attachments/assets/79aed9a4-1f6e-4d86-a383-947057bcc4f6" /> <img width="1444" height="1260" alt="image" src="https://github.com/user-attachments/assets/c19cac7b-3ddb-4505-bd66-703cb5d46347" />


<img width="1429" height="1171" alt="image" src="https://github.com/user-attachments/assets/d1fcff8d-6cbf-47dc-8fad-9ee112eaefa8" /> <img width="1438" height="1177" alt="image" src="https://github.com/user-attachments/assets/d02d1570-5992-49f3-89b4-139e9d5540d2" />





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

Use this docker-compose file:
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

### Then you can run `docker compose up -d` and the app should start on `http://127.0.0.1:5000` or `http://yourIp:5000`

### To update the container if an update is available, run `docker compose pull`

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

This project is licensed under the `Soffer Non-Commercial Source-Available License v1.0` - see the LICENSE file for details.

## Support

For support, please open an issue on the GitHub repository or contact me.
