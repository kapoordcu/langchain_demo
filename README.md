# LangChain Demo

Small examples for working with LangChain, chat models, embeddings, and prompts.

## Setup

From the project directory, create and activate a virtual environment:

```bash
cd /Users/gaurakap/Desktop/langchain_demo
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell, activate it with:

```powershell
.venv\Scripts\Activate.ps1
```

Install the Python dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Environment variables

Some demos use external model providers. Create a `.env` file in the project root and add only the keys required by the demo you run:

```env
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
GOOGLE_API_KEY=your_google_key
HUGGINGFACEHUB_API_TOKEN=your_hugging_face_token
```

`.env` is excluded from Git; never commit API keys.

## Run an example

With the environment activated, run a script such as:

```bash
python chatbot.py
```

When you are finished, leave the virtual environment with `deactivate`.
