
# Google Cloud Console Setup Blueprint

### 1. Project Initialization
* Open the Google Cloud Console dashboard.
* Click the project selector dropdown in the top-left corner.
* Click **New Project**, name it **GrandElevationSolar**, and click **Create**.
* Ensure your new project is active in the top dropdown selection.

### 2. Enable API Libraries
* Open the left-hand navigation sidebar.
* Select **APIs & Services** > **Library**.
* Search for **Gmail API** in the center search box.
* Click on the **Gmail API** card and click the blue **Enable** button.

### 3. Configure the OAuth Consent Screen
* Open the left sidebar and select **APIs & Services** > **OAuth consent screen** (or **Google Auth Platform**).
* Choose **External** for the User Type and click **Create**.
* Fill out the three required fields on the **Branding** tab:
  * **App name**: GrandElevationSolar
  * **User support email**: Select your own Gmail from the dropdown.
  * **Developer contact information**: Enter your own email address.
* Click **Save and Continue**.
* Click **Save and Continue** on the **Scopes** tab without adding anything.

### 4. Whitelist Test Accounts
* Navigate to the **Audience** (or **Test users**) sub-tab within the consent management dashboard.
* Find the **Test users** card section.
* Click the **+ Add Users** button.
* Input your target testing account address exactly: `okosadavid3@gmail.com`
* Click the blue **Save** button to lock in the permissions.

### 5. Generate System Credentials
* Open the left sidebar and select **APIs & Services** > **Credentials**.
* Click the **+ Create Credentials** button at the top center.
* Select **OAuth client ID** from the drop-down list options.
* Set the **Application type** dropdown to **Desktop Application**.
* Give the credential a name (e.g., "Desktop Client") and click **Create**.
* Click the **Download JSON** icon on the confirmation pop-up window.
* Rename that downloaded file to exactly `credentials.json` for your project directory.
