# Bluesky Scheduler

This application allows users to schedule posts for Bluesky, including the ability to upload images and specify alt text for each image. It's built using Streamlit and integrates with the Bluesky API.

## Features

- **Text Post Scheduling**: Schedule text posts with a limit of 300 characters.
- **Image Upload**: Upload images to be included in the scheduled posts.
- **Alt Text for Images**: Provide alt text for each uploaded image, enhancing accessibility.
- **PST Time Scheduling**: Schedule posts based on the Pacific Standard Time (PST) with conversion to UTC for accurate scheduling.

## Requirements:
- Python >= 3.7.6
- Packages listed in requirements.txt

## Setup

1. Clone the repository and navigate to the project directory.
2. Install the required packages using ```pip install -r requirements.txt```
3. Run the Streamlit application through ```streamlit run scheduler.py```

## Usage:

1. Go to Bluesky -> Settings -> Advanced -> App passwords.
2. Click 'Add an app password' and follow the instructions. Note down the password once it is generated since it cannot be viewed again.
3. In the Streamlit application, fill in the Bluesky Handle field with your bsky handle/username (e.g. yourname.bsky.social) and the Bluesky Password field with the app password you generated in Step 2.
4. You can then fill out the rest of the respective fields with post content, uoload images, add alt text for each image, set a scheduled post time, etc.

## Development Resources:
- https://github.com/bluesky-social/atproto-website/blob/main/examples/create_bsky_post.py
