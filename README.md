# Clickable Element Tester

A comprehensive tool for testing clickable elements on web pages, detecting dead clicks, and analyzing interactive elements with concurrent processing capabilities.

## Features

- **Concurrent Testing**: Tests multiple elements simultaneously using thread pools
- **Dead Click Detection**: Identifies non-functional clickable elements
- **Carousel Support**: Special handling for auto-scrolling carousels and banners
- **Comprehensive Reporting**: Detailed statistics and classification of clickable elements
- **Element Detection**: Finds all potentially clickable elements using multiple strategies
- **HTTP Status Checking**: Verifies link status codes where applicable

## Installation

1. **Prerequisites**:
   - Python 3.7+
   - Chrome browser
   - ChromeDriver (matching your Chrome version)

2. **Install dependencies**:
   ```bash
   pip install selenium requests concurrent-log-handler
