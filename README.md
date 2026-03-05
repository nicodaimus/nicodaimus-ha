# nicodAImus Home Assistant Integration

Privacy-first AI conversation agent for Home Assistant, powered by [nicodAImus](https://nicodaimus.com). In order for the integration to work you need a **passthrough API key** from [nicodAImus](https://nicodaimus.com/account/create/).

## Features

- **Voice Control** - Works with Home Assistant Assist for voice commands
- **Smart Home Control** - Turn on lights, check temperatures, control devices
- **Streaming Responses** - Real-time response streaming for a natural experience
- **Privacy First** - Your data stays private, no tracking, no profiling
- **Multi-language** - Supports all languages
- **Simple Setup** - Just enter your API key and you're ready to go

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations** > three-dot menu > **Custom repositories**
3. Add this repository URL with category **Integration**
4. Click **Install**
5. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/nicodaimus` folder to your `config/custom_components/` directory
2. Restart Home Assistant

## Setup

1. Go to **Settings** > **Devices & Services**
2. Click **+ Add Integration**
3. Search for **nicodAImus**
4. Enter your API key
5. Done!

Your API key must be in **passthrough mode** for Home Assistant integration.
Contact support@nicodaimus.com if you need help setting this up.

## Configuration

After setup, you can add conversation agents with different settings:

- **System Prompt** - Customize how the AI responds
- **Model** - Use `auto` (default) for automatic model selection
- **Temperature** - Control response randomness (0-2)
- **Max Tokens** - Limit response length
- **Home Assistant Control** - Enable device control via Assist

## Voice Setup

1. Go to **Settings** > **Voice assistants**
2. Create or edit an assistant
3. Set **Conversation agent** to your nicodAImus agent
4. Configure STT and TTS as desired

## Requirements

- Home Assistant 2025.4.0 or newer
- nicodAImus API key (passthrough mode)

## Support

- Documentation: [nicodaimus.com/docs/home-assistant](https://nicodaimus.com/docs/home-assistant)
- Issues: [GitHub Issues](https://github.com/nicodaimus/nicodaimus-ha/issues)
- Email: support@nicodaimus.com

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.
