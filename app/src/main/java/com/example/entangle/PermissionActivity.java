package com.example.entangle;

import android.content.Intent;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import androidx.appcompat.app.AppCompatActivity;

public class PermissionActivity extends AppCompatActivity {
    private static final int REQUEST_CODE = 100;
    private static final String TAG = "PermissionActivity";
    private MediaProjectionManager projectionManager;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_permission);

        Log.d(TAG, "onCreate called");

        projectionManager = (MediaProjectionManager)
                getSystemService(MEDIA_PROJECTION_SERVICE);

        // Request permission to capture screen
        startActivityForResult(
                projectionManager.createScreenCaptureIntent(),
                REQUEST_CODE
        );
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);

        Log.d(TAG, "onActivityResult: requestCode=" + requestCode + ", resultCode=" + resultCode);

        if (requestCode == REQUEST_CODE && resultCode == RESULT_OK) {
            Log.d(TAG, "Permission granted, starting ScreenMirrorService");

            // Create intent with extras
            Intent serviceIntent = new Intent(this, ScreenMirrorService.class);
            serviceIntent.putExtra("resultCode", resultCode);
            serviceIntent.putExtra("resultData", data);

            Log.d(TAG, "Starting foreground service");

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(serviceIntent);
            } else {
                startService(serviceIntent);
            }

            Log.d(TAG, "Service start command issued");
            finish();
        } else {
            Log.e(TAG, "Permission denied or cancelled");
        }
    }
}