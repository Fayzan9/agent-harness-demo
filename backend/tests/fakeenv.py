"""Import this first in a test: gives the app harmless settings so it can start without a real key.

Real environment variables beat the .env file, so these always win, and tests never reach a real model.
"""
import os

os.environ["OPENAI_API_BASE"] = "https://fake.example.test"
os.environ["OPENAI_API_KEY"] = "fake-key-for-tests"
os.environ["MODEL"] = "fake-model"
