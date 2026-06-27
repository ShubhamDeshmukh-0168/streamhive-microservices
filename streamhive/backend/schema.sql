CREATE DATABASE IF NOT EXISTS streamhive;
USE streamhive;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    full_name VARCHAR(150) DEFAULT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    address TEXT DEFAULT NULL,
    phone VARCHAR(20) DEFAULT NULL,
    otp_code VARCHAR(10) DEFAULT NULL,
    otp_expiry DATETIME DEFAULT NULL,
    last_login_otp_verified_at DATETIME DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pending_signups (
    email VARCHAR(150) PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    full_name VARCHAR(150) DEFAULT NULL,
    password_hash VARCHAR(255) NOT NULL,
    otp_code VARCHAR(10) NOT NULL,
    otp_expiry DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    item_id VARCHAR(100) NOT NULL,
    item_title VARCHAR(255) NOT NULL,
    item_thumbnail TEXT DEFAULT NULL,
    category VARCHAR(50) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_user_item (user_id, item_id),
    CONSTRAINT fk_watchlist_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
