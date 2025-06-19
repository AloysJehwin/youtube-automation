# n8n YouTube Automation

## Overview

This n8n workflow automates short video content generation for YouTube using:

* Telegram bot for playlist input
* Google Sheets for content
* PIAPI for image generation
* ElevenLabs for audio generation
* Google Drive for storing assets

## Features

* Telegram interaction with playlist selection
* Fetch data from Google Sheets
* Generate images using AI (txt2img)
* Generate audio narration
* Upload all outputs to Google Drive
* Update status back to Google Sheets

## Prerequisites

* n8n instance (self-hosted or cloud)
* Telegram bot token
* Google API credentials
* PIAPI and ElevenLabs API keys

## Setup

1. Configure Telegram Trigger with your bot
2. Connect Google Sheets and Drive credentials
3. Replace API keys in HTTP Request nodes
4. Format Google Sheet with required columns:

   * Video title, Image\_1\_prompt to Image\_8\_prompt, Audio Content

## Flow Summary

* User selects playlist on Telegram
* Workflow fetches corresponding content from Google Sheets
* Images and audio are generated
* Assets are uploaded to Drive
* Google Sheet is updated with links
* Telegram confirms each step

## Notes

* Ensure API services are connected in n8n
* Wait nodes handle async image generation

## Author

Aloys Jehwin
[aloysjehwin.com](https://aloysjehwin.com)
