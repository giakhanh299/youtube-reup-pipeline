REUP PIPELINE V2 - GOOGLE SHEET CONTROL ALL

1) Cài thư viện:
   pip install -r requirements.txt

2) Tạo Google Sheet có đúng các tab:
   - CHANNEL_CONFIG
   - VOICE_CONFIG
   - MUSIC_PACK
   - OVERLAY_PACK
   - RENDER_PRESET
   - VIDEO_QUEUE

   Có thể copy header + dữ liệu mẫu từ thư mục sheets_templates/*.csv.

3) Tạo Google Cloud service account JSON, tải về máy.
   Sau đó share Google Sheet cho email client_email trong file JSON.

4) Sửa configs/settings.json:
   - spreadsheet_id: ID Google Sheet
   - service_account_json: đường dẫn file JSON service account
   - google_key_dir: thư mục chứa key Google TTS cũ nếu còn dùng engine=google

5) Cách chạy:
   python pipeline.py

6) Chế độ chạy:
   - process_queue_only = false:
     Mỗi kênh quét input_folder trong CHANNEL_CONFIG, tự bắt video với .srt/.txt cùng tên.

   - process_queue_only = true:
     Chỉ xử lý các dòng VIDEO_QUEUE có status=NEW, sau đó cập nhật READY_UPLOAD/ERROR.

7) Cách đặt file để tự bắt:
   abc.mp4 + abc_vi.srt
   abc.mp4 + abc.srt
   abc.mp4 + abc.txt

8) Google Sheet điều khiển:
   - Đổi giọng: sửa voice_id trong CHANNEL_CONFIG hoặc sửa thông số VOICE_CONFIG.
   - Đổi logo: sửa OVERLAY_PACK.logo_path.
   - Đổi nhạc: sửa MUSIC_PACK.music_path.
   - Đổi render: sửa RENDER_PRESET.
   - Đổi kênh output: sửa CHANNEL_CONFIG.output_folder.
