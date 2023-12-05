import datetime
import re
import requests
from typing import Dict, List

import pytz
import streamlit as st
from apscheduler.schedulers.background import BackgroundScheduler

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Streamlit UI setup
st.title("Bluesky Post Scheduler")
bsky_handle = st.text_input("Bluesky Handle")
bsky_password = st.text_input("Bluesky Password", type="password")
post_content = st.text_area("Post Content")

# Add an image upload option
uploaded_images = st.file_uploader("Upload Images", accept_multiple_files=True, type=["png", "jpg", "jpeg", "webp"])

# Create a placeholder to dynamically add alt text inputs
alt_text_placeholder = st.empty()

# Collect alt texts
image_alt_texts = []

if uploaded_images:
    with alt_text_placeholder.container():
        for i, img in enumerate(uploaded_images):
            alt_text = st.text_input(f"Alt text for Image {i+1} ({img.name})", key=f"img_{i}")
            image_alt_texts.append(alt_text)

scheduled_date = st.date_input("Scheduled Date", min_value=datetime.datetime.today())

# Separate inputs for hours and minutes
hour = st.selectbox("Hour", list(range(24)), format_func=lambda x: f'{x:02d}')
minute = st.selectbox("Minute", list(range(0, 60, 1)), format_func=lambda x: f'{x:02d}')

submit = st.button("Schedule Post")

def parse_mentions(text: str) -> List[Dict]:
    spans = []
    # regex based on: https://atproto.com/specs/handle#handle-identifier-syntax
    mention_regex = rb"[$|\W](@([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
    text_bytes = text.encode("UTF-8")
    for m in re.finditer(mention_regex, text_bytes):
        spans.append(
            {
                "start": m.start(1),
                "end": m.end(1),
                "handle": m.group(1)[1:].decode("UTF-8"),
            }
        )
    return spans


def test_parse_mentions():
    assert parse_mentions("prefix @handle.example.com @handle.com suffix") == [
        {"start": 7, "end": 26, "handle": "handle.example.com"},
        {"start": 27, "end": 38, "handle": "handle.com"},
    ]
    assert parse_mentions("handle.example.com") == []
    assert parse_mentions("@bare") == []
    assert parse_mentions("💩💩💩 @handle.example.com") == [
        {"start": 13, "end": 32, "handle": "handle.example.com"}
    ]
    assert parse_mentions("email@example.com") == []
    assert parse_mentions("cc:@example.com") == [
        {"start": 3, "end": 15, "handle": "example.com"}
    ]


def parse_urls(text: str) -> List[Dict]:
    spans = []
    # partial/naive URL regex based on: https://stackoverflow.com/a/3809435
    # tweaked to disallow some training punctuation
    url_regex = rb"[$|\W](https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*[-a-zA-Z0-9@%_\+~#//=])?)"
    text_bytes = text.encode("UTF-8")
    for m in re.finditer(url_regex, text_bytes):
        spans.append(
            {
                "start": m.start(1),
                "end": m.end(1),
                "url": m.group(1).decode("UTF-8"),
            }
        )
    return spans

def test_parse_urls():
    assert parse_urls(
        "prefix https://example.com/index.html http://bsky.app suffix"
    ) == [
        {"start": 7, "end": 37, "url": "https://example.com/index.html"},
        {"start": 38, "end": 53, "url": "http://bsky.app"},
    ]
    assert parse_urls("example.com") == []
    assert parse_urls("💩💩💩 http://bsky.app") == [
        {"start": 13, "end": 28, "url": "http://bsky.app"}
    ]
    assert parse_urls("runonhttp://blah.comcontinuesafter") == []
    assert parse_urls("ref [https://bsky.app]") == [
        {"start": 5, "end": 21, "url": "https://bsky.app"}
    ]
    # note: a better regex would not mangle these:
    assert parse_urls("ref (https://bsky.app/)") == [
        {"start": 5, "end": 22, "url": "https://bsky.app/"}
    ]
    assert parse_urls("ends https://bsky.app. what else?") == [
        {"start": 5, "end": 21, "url": "https://bsky.app"}
    ]

def parse_facets(pds_url: str, text: str) -> List[Dict]:
    """
    parses post text and returns a list of app.bsky.richtext.facet objects for any mentions (@handle.example.com) or URLs (https://example.com)

    indexing must work with UTF-8 encoded bytestring offsets, not regular unicode string offsets, to match Bluesky API expectations
    """
    facets = []
    for m in parse_mentions(text):
        resp = requests.get(
            pds_url + "/xrpc/com.atproto.identity.resolveHandle",
            params={"handle": m["handle"]},
        )
        # if handle couldn't be resolved, just skip it! will be text in the post
        if resp.status_code == 400:
            continue
        did = resp.json()["did"]
        facets.append(
            {
                "index": {
                    "byteStart": m["start"],
                    "byteEnd": m["end"],
                },
                "features": [{"$type": "app.bsky.richtext.facet#mention", "did": did}],
            }
        )
    for u in parse_urls(text):
        facets.append(
            {
                "index": {
                    "byteStart": u["start"],
                    "byteEnd": u["end"],
                },
                "features": [
                    {
                        "$type": "app.bsky.richtext.facet#link",
                        # NOTE: URI ("I") not URL ("L")
                        "uri": u["url"],
                    }
                ],
            }
        )
    return facets

def parse_uri(uri: str) -> Dict:
    if uri.startswith("at://"):
        repo, collection, rkey = uri.split("/")[2:5]
        return {"repo": repo, "collection": collection, "rkey": rkey}
    elif uri.startswith("https://bsky.app/"):
        repo, collection, rkey = uri.split("/")[4:7]
        if collection == "post":
            collection = "app.bsky.feed.post"
        elif collection == "lists":
            collection = "app.bsky.graph.list"
        elif collection == "feed":
            collection = "app.bsky.feed.generator"
        return {"repo": repo, "collection": collection, "rkey": rkey}
    else:
        raise Exception("unhandled URI format: " + uri)
    
def upload_file(pds_url, access_token, filename, img_bytes) -> Dict:
    # Determine the file's mimetype based on its extension
    suffix = filename.split(".")[-1].lower()
    mimetype = "application/octet-stream"  # Default mimetype
    if suffix == "png":
        mimetype = "image/png"
    elif suffix in ["jpeg", "jpg"]:
        mimetype = "image/jpeg"
    elif suffix == "webp":
        mimetype = "image/webp"

    # Sending the request to upload the file
    response = requests.post(
        pds_url + "/xrpc/com.atproto.repo.uploadBlob",
        headers={
            "Content-Type": mimetype,
            "Authorization": "Bearer " + access_token,
        },
        data=img_bytes
    )
    response.raise_for_status()

    # Return the response containing blob information
    return response.json()["blob"]

def send_post(bsky_handle, bsky_password, post_content, uploaded_images, image_alt_texts):
    # Function to login to Bluesky and get session token
    def bsky_login_session(pds_url, handle, password):
        response = requests.post(
            pds_url + "/xrpc/com.atproto.server.createSession",
            json={"identifier": handle, "password": password},
        )
        response.raise_for_status()
        return response.json()

    # Parsing and preparing post content with facets (mentions and URLs)
    def prepare_post_content(pds_url, text):
        # The functions `parse_mentions` and `parse_urls` from your script would be used here
        # Additionally, `parse_facets` would be used to convert mentions and URLs into facets
        # For simplicity, this example does not include these complex parsing functions
        # Assuming `parse_facets` returns a list of facet dictionaries
        facets = parse_facets(pds_url, text)
        return {
            "text": text,
            "facets": facets
        }

    # Base URL for Bluesky API
    pds_url = "https://bsky.social"

    # Login and get session token
    session = bsky_login_session(pds_url, bsky_handle, bsky_password)
    access_token = session["accessJwt"]

    # Current UTC timestamp in ISO 8601 format
    now_utc = datetime.datetime.now(pytz.utc).isoformat()

    # Prepare the post content
    post_data = prepare_post_content(pds_url, post_content)
    post_data['createdAt'] = now_utc  # Add 'createdAt' property

    # Handle image upload
    if uploaded_images:
        image_blobs = []
        for img, alt_text in zip(uploaded_images, image_alt_texts):
            img_bytes = img.getvalue()
            if len(img_bytes) > 1000000:  # 1MB size limit check
                raise Exception(f"Image file size too large: {len(img_bytes)} bytes")
            blob = upload_file(pds_url, access_token, img.name, img_bytes)
            image_blobs.append({"alt": alt_text, "image": blob})

        if image_blobs:
            post_data['embed'] = {
                "$type": "app.bsky.embed.images",
                "images": image_blobs
            }

    # Make the post request
    response = requests.post(
        pds_url + "/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": "Bearer " + access_token},
        json={
            "repo": session["did"],
            "collection": "app.bsky.feed.post",
            "record": post_data
        }
    )

    # Check if the post was successful
    if response.status_code == 200:
        print("Post created successfully.")
    else:
        print("Error creating post:", response.text)

if submit:
    if len(post_content) > 300:
        st.error("Post content exceeds 300 characters.")
    else:
        # Combine date and time, and convert to UTC
        pst_zone = pytz.timezone('America/Los_Angeles')
        scheduled_time = datetime.time(hour, minute)
        scheduled_datetime_pst = datetime.datetime.combine(scheduled_date, scheduled_time)
        scheduled_datetime_utc = pst_zone.localize(scheduled_datetime_pst).astimezone(pytz.utc)

        # Validation and scheduling logic
        if scheduled_datetime_utc <= datetime.datetime.now(pytz.utc):
            st.error("Scheduled time must be in the future.")
        else:
            # Pass uploaded images to the send_post function
            scheduler.add_job(send_post, 'date', run_date=scheduled_datetime_utc, 
                            args=[bsky_handle, bsky_password, post_content, uploaded_images, image_alt_texts])
            st.success("Post scheduled successfully.")