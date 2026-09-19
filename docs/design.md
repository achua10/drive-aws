Region: ap-south-1
Naming: drive-<env>-<thing>
Record fields: file ID, original name, size, content type, S3 key, upload time.
S3 key: built from the file ID, like uploads/<file_id>, never from the user's file name.
Link expiry: [5 minutes].
Max file size: [5 MB].
Routes: upload request, list files, download link, delete.