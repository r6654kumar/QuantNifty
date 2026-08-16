function pingRender() {
  const url = "https://quantnifty.onrender.com/api/health";

  try {
    const response = UrlFetchApp.fetch(url, {
      method: "get",
      muteHttpExceptions: true
    });

    const status = response.getResponseCode();
    const body = response.getContentText();

    console.log("HTTP Status: " + status);
    console.log("Response: " + body);

  } catch (error) {
    console.error("Render ping failed: " + error);
  }
}
