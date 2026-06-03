 <img src="https://github.com/user-attachments/assets/153ecfd4-073b-47f9-bc8d-c3f1e0502276" width="400" />  <img src="https://github.com/user-attachments/assets/3ac23156-955c-468e-ab71-87fd96dc0349" width="400" /> 



# Spotify Stats Tracker
### If you found [this repository](https://github.com/TzurSoffer/SpotifyStatsTracker) useful, please give it a ⭐!.
A web application that allows users to track and analyze their Spotify listening habits and statistics **without Spotify Premium**.

## Features

- View your top songs.
- View your top artists.
- See your listening history.

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
    environment:
      - FLASK_APP=app.py
      - PYTHONUNBUFFERED=1
    restart: always
    # Optional: uncomment for debug mode
    # environment:
    #   - FLASK_DEBUG=1
```

Then you can run `docker compose up -d` and the app should start on `127.0.0.1:5000` or `yourIp:5000`

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
