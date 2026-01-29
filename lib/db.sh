#!/bin/bash
# SQLite database functions for transcribe

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

# Initialize the database schema
init_db() {
    ensure_config_dir

    sqlite3 "$DB_FILE" <<'EOF'
CREATE TABLE IF NOT EXISTS audio_files (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    transcribed_at DATETIME,
    transcript_path TEXT
);

CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    audio_file_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    labeled_at DATETIME,
    summarized_at DATETIME,
    summary_path TEXT,
    FOREIGN KEY (audio_file_id) REFERENCES audio_files(id)
);

CREATE INDEX IF NOT EXISTS idx_audio_files_path ON audio_files(path);
CREATE INDEX IF NOT EXISTS idx_transcripts_path ON transcripts(path);
CREATE INDEX IF NOT EXISTS idx_transcripts_labeled ON transcripts(labeled_at);
EOF
}

# Add or update an audio file record
db_add_audio() {
    local path="$1"
    local filename=$(basename "$path")

    sqlite3 "$DB_FILE" "INSERT OR IGNORE INTO audio_files (path, filename) VALUES ('$path', '$filename');"
}

# Mark audio file as transcribed
db_mark_transcribed() {
    local audio_path="$1"
    local transcript_path="$2"

    sqlite3 "$DB_FILE" "UPDATE audio_files SET transcribed_at = CURRENT_TIMESTAMP, transcript_path = '$transcript_path' WHERE path = '$audio_path';"
}

# Add a transcript record
db_add_transcript() {
    local path="$1"
    local audio_file_id="$2"

    sqlite3 "$DB_FILE" "INSERT OR IGNORE INTO transcripts (path, audio_file_id) VALUES ('$path', $audio_file_id);"
}

# Get audio file ID by path
db_get_audio_id() {
    local path="$1"
    sqlite3 "$DB_FILE" "SELECT id FROM audio_files WHERE path = '$path';"
}

# Mark transcript as labeled
db_mark_labeled() {
    local transcript_path="$1"
    sqlite3 "$DB_FILE" "UPDATE transcripts SET labeled_at = CURRENT_TIMESTAMP WHERE path = '$transcript_path';"
}

# Mark transcript as summarized
db_mark_summarized() {
    local transcript_path="$1"
    local summary_path="$2"

    sqlite3 "$DB_FILE" "UPDATE transcripts SET summarized_at = CURRENT_TIMESTAMP, summary_path = '$summary_path' WHERE path = '$transcript_path';"
}

# Get unlabeled transcripts
db_get_unlabeled() {
    sqlite3 -separator '|' "$DB_FILE" "SELECT path FROM transcripts WHERE labeled_at IS NULL ORDER BY created_at;"
}

# Get unsummarized but labeled transcripts
db_get_unsummarized() {
    sqlite3 -separator '|' "$DB_FILE" "SELECT path FROM transcripts WHERE labeled_at IS NOT NULL AND summarized_at IS NULL ORDER BY created_at;"
}

# Get all audio files with status
db_list_audio_files() {
    sqlite3 -separator '|' "$DB_FILE" "SELECT path, filename, CASE WHEN transcribed_at IS NOT NULL THEN 'transcribed' ELSE 'pending' END as status, added_at FROM audio_files ORDER BY added_at DESC;"
}

# Get all transcripts with status
db_list_transcripts() {
    sqlite3 -separator '|' "$DB_FILE" "SELECT path, CASE WHEN summarized_at IS NOT NULL THEN 'summarized' WHEN labeled_at IS NOT NULL THEN 'labeled' ELSE 'unlabeled' END as status, created_at FROM transcripts ORDER BY created_at DESC;"
}

# Delete audio file record
db_delete_audio() {
    local path="$1"
    sqlite3 "$DB_FILE" "DELETE FROM audio_files WHERE path = '$path';"
}

# Delete transcript record
db_delete_transcript() {
    local path="$1"
    sqlite3 "$DB_FILE" "DELETE FROM transcripts WHERE path = '$path';"
}

# Check if audio file exists in DB
db_audio_exists() {
    local path="$1"
    local count=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM audio_files WHERE path = '$path';")
    [[ "$count" -gt 0 ]]
}

# Check if audio file has been transcribed
db_is_transcribed() {
    local path="$1"
    local result=$(sqlite3 "$DB_FILE" "SELECT transcribed_at FROM audio_files WHERE path = '$path';")
    [[ -n "$result" ]]
}
