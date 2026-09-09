# SCCM Maxi Tools

A comprehensive Python Tkinter GUI application for Microsoft System Center Configuration Manager (SCCM) administration and management.

![Python](https://img.shields.io/badge/Python-3.14+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)

## 📋 Overview

SCCM Maxi Tools provides a modern, user-friendly desktop application for managing SCCM deployments, collections, variables, and logs. It integrates multiple SCCM management utilities into a single, cohesive interface with dark/light theme support and responsive design.

## ✨ Features

### Core Tools

#### 🎯 Copy Deployment (Copy Deplmt)
- Copy deployment names from SCCM collections
- Support for multiple deployment types:
  - Task Sequences
  - Software Update Groups
  - Applications
  - Programs
  - Baselines
- Advanced type detection and resolution
- Filter deployments by collection
- View deployment details
- Clipboard export

#### 🧩 Collection Member (CollMember)
- Filter and search SCCM collections
- View collection membership
- Add/remove devices or users
- Import members from CSV
- Support for Device and User collections

#### 🏷️ Collection Variable (CollVariable)
- Manage collection variables
- Variable numbering and renumbering
- Replace variable values
- Pattern-based variable management

#### 📊 Last 10 Deployments (Last10DPLM)
- Quick view of recent deployments
- Deployment status monitoring
- Quick access to common deployments

#### 📋 CMTrace Integration
- Embedded CMTrace viewer in WebView2
- Log file parsing and analysis
- Error code lookup
- Real-time log analysis

### User Interface

- **Responsive Design**: Automatically adapts to window size (compact/wide modes)
- **Theme Support**: Light and Dark themes with real-time switching
- **Tabbed Interface**: Easy navigation between tools (Tools, PS1, Infra Tools, CMTrace)
- **Modern UI Components**: Custom canvas-based buttons, treeview displays, progress indicators
- **Profile Management**: Save and switch between SCCM server profiles

### Additional Features

- SCCM Connection verification
- PowerShell script generation and execution
- Async script execution with output streaming
- Profile management (multiple SCCM servers)
- Settings persistence
- Comprehensive error handling and logging

## 🚀 Getting Started

### Prerequisites

- Python 3.14+
- Windows OS (for SCCM integration)
- SCCM ConfigurationManager module
- Pillow (PIL) for image processing
- tkinter (included with Python)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/izakenagi/SCCMTools.git
   cd SCCMTools
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python app.py
   ```

### Requirements

See `requirements.txt`:
- Pillow (image processing)
- pythonnet (for .NET integration, optional)
- webview (for CMTrace WebView2, optional)

## 📁 Project Structure

```
SCCM Maxi Tools/
├── app.py                      # Main application (5600+ lines)
├── test_app.py                 # Unit tests (15+ test cases)
├── requirements.txt            # Python dependencies
├── profiles.json               # SCCM profile configuration
├── settings.json               # User preferences
├── ps1/                        # PowerShell scripts directory
├── CMTraceDev/                 # CMTrace web application
│   ├── src/                   # Web source files
│   ├── docker-compose.yml     # Docker setup
│   └── README.md              # CMTrace documentation
├── Infra TOOLS/               # Infrastructure utilities
│   ├── ClientTools/           # SCCM client tools
│   ├── ServerTools/           # SCCM server tools
│   └── ServiceConnectionTool/ # Service connection utilities
├── my-app/                     # Next.js web application
│   ├── app/                   # Next.js app directory
│   ├── public/                # Static assets
│   └── package.json           # Node.js dependencies
└── README.md                   # This file
```

## 🧪 Testing

Run the comprehensive test suite:

```bash
python -m unittest test_app.py
```

### Test Coverage

The test suite includes:
- ✅ Copy Deployment type resolution
- ✅ Copy Deployment filtering and selection
- ✅ Collection Variable numbering
- ✅ Responsive layout switching
- ✅ UI element functionality
- ✅ Script generation validation
- ✅ Collection filtering

Run specific test:
```bash
python -m unittest test_app.RunScriptButtonTests
```

## 🔧 Configuration

### SCCM Profile Setup

Create/edit `profiles.json`:
```json
{
  "profiles": [
    {
      "name": "Production",
      "server": "SCCM-SERVER.domain.com",
      "site_code": "PS1"
    },
    {
      "name": "Development",
      "server": "DEV-SCCM.domain.com",
      "site_code": "DEV"
    }
  ],
  "active_profile": "Production"
}
```

### User Settings

Settings are automatically saved to `settings.json`:
- Theme preference (light/dark)
- Active profile
- PS1 script search path
- Window size and position

## 📖 Usage Examples

### Copy a Deployment

1. Click **Copy Deplmt** in the Tools menu
2. Enter a collection filter (e.g., "SRC-")
3. Select deployment type (Task Sequence, Application, etc.)
4. Click **Filter** to load deployments
5. Check the deployments to copy
6. Click **Copy** to copy names to clipboard

### Add Collection Members

1. Click **CollMember** in the Tools menu
2. Filter and select a collection
3. Click **Add Device** or **Add User**
4. Paste or import member names
5. Click **Save** to add members

### Manage Collection Variables

1. Click **CollVariable** in the Tools menu
2. Filter collections by name
3. Select a collection and variable
4. Use RE-NUMBER to renumber variables
5. Use REPLACE to update values

## 🏗️ Architecture

### Class Structure

**SCCMToolboxApp (tk.Tk)**
- Main application window
- UI initialization and management
- Event handling
- SCCM operations

### Key Methods

- `_build_copy_deployment_candidates_script()` - Generates PowerShell for deployment queries
- `filter_copy_deployment_candidates()` - Filters deployments by type
- `copy_deployment_value()` - Exports deployment names
- `check_sccm_connection()` - Verifies SCCM connectivity
- `_apply_responsive_layout()` - Handles UI responsiveness
- `apply_theme()` - Theme switching

### Theme System

- **LIGHT_THEME**: Primary color #007348, white surfaces
- **DARK_THEME**: Dark surfaces with accent colors
- Colors defined as dictionaries with semantic names

## 🔄 PowerShell Integration

The application dynamically generates PowerShell scripts for:
- SCCM module loading
- Deployment queries
- Collection filtering
- Member management
- Configuration item deployment

Example generated script features:
- Robust error handling
- Type mapping and conversion
- Property alias resolution
- JSON output for parsing

## 🐛 Known Issues & Limitations

- CMTrace WebView2 requires Windows WebView2 Runtime
- SCCM ConfigurationManager module required for full functionality
- Some features require Administrator privileges
- Large deployments (>1000 items) may impact UI responsiveness

## 🚧 Development

### Adding New Tools

1. Create tool panel in `build_ui()`
2. Add mode to `vertical_menu_items`
3. Implement tool methods
4. Add icon to `vertical_menu_icons`
5. Handle mode in `configure_tools_mode()`
6. Add tests to `test_app.py`

### Code Style

- Python 3.14+ type hints
- PEP 8 compliance
- Docstrings for public methods
- Comments for complex logic

## 📦 Deployment

### Build Executable

Use PyInstaller to create standalone executable:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --add-data "seguiemj.ttf:." app.py
```

### System Requirements for Deployment

- Windows 7+
- .NET Framework 4.5+
- SCCM ConfigurationManager module
- WebView2 Runtime (for CMTrace feature)

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Contribution Guidelines

- Write tests for new features
- Update documentation
- Follow existing code style
- Test on Windows with SCCM access

## 📝 Changelog

### Version 1.0.0
- Initial release
- Copy Deployment tool with advanced type detection
- Collection Member management
- Collection Variable management
- CMTrace integration
- Dark/Light theme support
- Responsive UI design
- 15+ unit tests
- Complete PowerShell integration

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.


## 🙏 Acknowledgments

- SCCM Community for best practices
- Tkinter documentation and examples
- CMTrace original developers
- Infrastructure Tools contributors


## 🔗 Links

- **GitHub Repository**: https://github.com/izakenagi/SCCMTools
- **SCCM Documentation**: https://docs.microsoft.com/en-us/mem/configmgr/
- **Python Documentation**: https://docs.python.org/3/
- **Tkinter Tutorial**: https://docs.python.org/3/library/tkinter.html

---
