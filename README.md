# March Madness Tournament Simulator

A Python-based web application to simulate NCAA March Madness tournaments using Elo-based team ratings. Pulls statistical data from multiple sources and predicts likely winners.

## Features
- Elo rating system for team strength calculation
- Tournament bracket simulation
- Historical data analysis
- Web interface for interactive simulations

## Setup

### Prerequisites
- Python 3.8+
- Node.js 16+ (for frontend)
- RapidAPI account (for data APIs)

### Backend Setup
1. Navigate to the `backend` directory:
   ```bash
   cd backend
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the Flask app:
   ```bash
   python app.py
   ```

### Frontend Setup
1. Navigate to the `frontend` directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the development server:
   ```bash
   npm start
   ```

## Project Structure
- `backend/` - Flask API server
- `frontend/` - React web application
- `data/` - Cached data files
- `tests/` - Unit tests
- `docs/` - Documentation

## Data Sources
- Sports-Reference.com (historical data via scraping)
- RapidAPI College Basketball APIs (current data)
- ESPN APIs (if available)

## License
This project is for educational and personal use. Check data source terms for commercial use.