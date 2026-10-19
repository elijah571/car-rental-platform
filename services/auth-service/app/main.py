from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def get_messge():
  return {"message": "Hello World"}
