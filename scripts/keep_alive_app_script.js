/**
 * Google Apps Script for keeping the Render server alive.
 * 
 * Deployment Instructions:
 * 1. Go to https://script.google.com/ and create a new project.
 * 2. Paste this entire code into Code.gs.
 * 3. Run `pingRender` manually once to authorize and confirm it works. 
 *    You should see HTTP 200 and the response in the Execution Log.
 * 
 * Automating with a Trigger:
 * 1. On the left sidebar, click the ⏰ Triggers icon.
 * 2. Click "+ Add Trigger" in the bottom-right.
 * 3. Configure as follows:
 *    - Choose which function to run: pingRender
 *    - Choose which deployment should run: Head
 *    - Select event source: Time-driven
 *    - Select type of time based trigger: Minutes timer
 *    - Select minute interval: Every 10 minutes (or Every 5 minutes)
 * 4. Click Save.
 * 
 * Note: After creating the trigger, don't manually run it repeatedly. Let the trigger do the work.
 * After ~10–15 minutes, check Apps Script -> Executions to see the success logs.
 */

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
