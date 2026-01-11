# Development Setup

This document describes how to set up your development environment to contribute to the project.

## Table of Contents
- [Development Setup](#development-setup)
  - [Table of Contents](#table-of-contents)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Installation](#2-installation)
  - [3. Notes](#3-notes)


##  1. <a name='Prerequisites'></a>Prerequisites

- Node.js 24.x
- Python 3.12

##  2. <a name='Installation'></a>Installation

1. Clone the repository
2. Install the dependencies

   1. Python:

      1. Create a virtual environment
         ```bash
         python -m venv .venv
         ```
      2. Activate the virtual environment
         - Linux / macOS
         ```bash
         source .venv/bin/activate
         ```
         - Windows
         ```bash
         .venv\Scripts\activate
         ```
      3. Install the dependencies
         ```bash
         pip install -r requirements.txt
         ```

   2. Node:

      1. Enter the `gui` directory
         ```bash
         cd gui
         ```
      2. Install the dependencies
         ```bash
         npm install
         ```

3. Start the development server

   When inside the `gui` directory, run the following command to start the development server:

   ```bash
   npm run dev
   ```

##  3. <a name='Notes'></a>Notes

The virtual environment needs to be in the project root directory. Either called `.venv` or `venv`. As this is currently the only way for electron to run the python script with the required dependencies.
