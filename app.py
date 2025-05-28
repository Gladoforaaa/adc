import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import requests

# --- Configs ---
st.set_page_config(page_title="Our Love Story", layout="centered")

# Your Google Sheet ID and Drive folder ID (update with your folder)
SHEET_ID = "1OtTJoIwh-3HRXgSW5GwdY4DfaYg8NaLVcxnfnEwQCNw"
DRIVE_FOLDER_ID = "1xf1TWo28QhwUE678fCo3SxWTWqBZKCfw"  # <-- Replace this!
def get_messages(sheet_id, sheet_name="Sheet1"):
    try:
        sheet_client, _ = get_gsheet_client()  # Unpack correctly
        worksheet = sheet_client.open_by_key(sheet_id).worksheet(sheet_name)
        records = worksheet.get_all_records()
        return pd.DataFrame(records)
    except Exception as e:
        st.error(f"Could not load messages: {e}")
        return pd.DataFrame()


def add_message(sheet_id, name, message, sheet_name="Sheet1"):
    try:
        sheet_client, _ = get_gsheet_client()  # Unpack correctly
        worksheet = sheet_client.open_by_key(sheet_id).worksheet(sheet_name)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        worksheet.append_row([name, message, timestamp])
        st.success("Your message was sent! 💌")
    except Exception as e:
        st.error(f"Could not send message: {e}")

# Authenticate and create Google Sheets client
def get_gsheet_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive.appdata"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name("loveapp-key.json", scope)
    client = gspread.authorize(creds)
    return client, creds

# Create Google Drive service client
def get_drive_service(creds):
    service = build('drive', 'v3', credentials=creds)
    return service

# Upload file to Google Drive folder, returns public URL
def upload_file_to_drive(service, file_bytes, filename, mimetype):
    file_metadata = {
        'name': filename,
        'parents': [DRIVE_FOLDER_ID]
    }
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mimetype)
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()

    # Make file publicly readable
    permission = {
        'type': 'anyone',
        'role': 'reader',
    }
    service.permissions().create(fileId=file['id'], body=permission).execute()

    # ✅ Construct a proper public viewable image URL
    file_id = file['id'].strip()  # <- ensures no trailing spaces or characters
    return f"https://drive.google.com/uc?export=view&id={file['id'].strip()}"



def add_photo_record(sheet_client, sheet_id, url, date, time, description, sheet_name="Photos"):
    try:
        sheet = sheet_client.open_by_key(sheet_id).worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        # Create the sheet and add headers
        sheet = sheet_client.open_by_key(sheet_id).add_worksheet(title=sheet_name, rows="100", cols="4")
        sheet.append_row(["image_url", "date", "time", "description"])
    
    sheet.append_row([url, date, time, description])


# Load photos metadata
def get_photos(sheet_client, sheet_id, sheet_name="Photos"):
    sheet = sheet_client.open_by_key(sheet_id).worksheet(sheet_name)

    # Ensure headers exist and are correct
    headers = sheet.row_values(1)
    expected = ["image_url", "date", "time", "description"]

    if headers != expected:
        sheet.update('A1:D1', [expected])
        return pd.DataFrame(columns=expected)

    records = sheet.get_all_records()
    df = pd.DataFrame(records)

    # Ensure all expected columns are present in DataFrame
    for col in expected:
        if col not in df.columns:
            df[col] = ""

    return df

# --- Streamlit UI ---
st.title("💖 Our Love Story with Photos")

tab1, tab2, tab3 = st.tabs(["💌 Message Board", "📸 Upload Photo", "🖼️ View Timeline"])

# --- Messages Tab ---

with tab1:
    st.subheader("Leave a Love Note 💖")
    name = st.text_input("Your name", max_chars=30)
    message = st.text_area("Your message", max_chars=200)

    if st.button("Send"):
        if name and message:
            add_message(SHEET_ID, name, message)
        else:
            st.warning("Please enter both name and message!")
    st.subheader("Latest Messages 📬")
    messages_df = get_messages(SHEET_ID)

    if not messages_df.empty:
        for _, row in messages_df[::-1].iterrows():
            st.markdown(f"**{row['name']}** wrote:")
            st.info(row["message"])
            st.caption(row["timestamp"])
    else:
        st.info("No messages yet. Be the first to write one!")

# --- Upload Photo Tab ---
with tab2:
    st.subheader("Upload a Photo to Your Timeline")

    uploaded_file = st.file_uploader("Choose an image", type=["png", "jpg", "jpeg", "gif"])
    date_input = st.date_input("Select date")
    time_input = st.time_input("Select time")
    description = st.text_area("Write a description", max_chars=300)

    if st.button("Upload Photo"):
        if uploaded_file is not None and description.strip():
            # Prepare credentials and services
            sheet_client, creds = get_gsheet_client()
            drive_service = get_drive_service(creds)

            # Upload file to Drive
            file_bytes = uploaded_file.read()
            filename = uploaded_file.name
            mimetype = uploaded_file.type

            try:
                url = upload_file_to_drive(drive_service, file_bytes, filename, mimetype)
                dt_str = f"{date_input} {time_input.strftime('%H:%M:%S')}"

                add_photo_record(sheet_client, SHEET_ID, url, str(date_input), time_input.strftime("%H:%M:%S"), description)

                st.success("Photo uploaded and saved to timeline!")
                st.image(file_bytes)
            except Exception as e:
                st.error(f"Upload failed: {e}")
        else:
            st.warning("Please upload an image and enter a description.")


# --- View Timeline Tab ---
with tab3:
    st.subheader("Timeline of Photos")

    try:
        sheet_client, _ = get_gsheet_client()
        df_photos = get_photos(sheet_client, SHEET_ID)
        if df_photos.empty:
            st.info("No photos uploaded yet.")
        else:
            # Sort by date & time descending
            df_photos['datetime'] = pd.to_datetime(df_photos['date'] + ' ' + df_photos['time'])
            df_photos = df_photos.sort_values(by='datetime', ascending=False)

            for _, row in df_photos.iterrows():
                st.markdown(f"**{row['date']} {row['time']}**")

                try:
                    response = requests.get(row['image_url'])
                    if response.status_code == 200:
                        st.image(response.content, use_container_width=True)
                    else:
                        st.error("Failed to load image from Drive.")
                except Exception as e:
                    st.error(f"Error loading image: {e}")

                st.write(row['description'])
                st.markdown("---")

    except Exception as e:
        st.error(f"Could not load timeline: {e}")
