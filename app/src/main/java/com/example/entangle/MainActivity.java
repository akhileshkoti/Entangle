package com.example.entangle;

import android.content.Intent;
import android.os.Bundle;
import android.widget.Button;
import android.widget.TextView;
import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        TextView statusText = findViewById(R.id.status_text);
        Button startButton = findViewById(R.id.start_button);

        statusText.setText("Screen Mirror Server");

        startButton.setOnClickListener(v -> {
            // Start the permission activity which will handle streaming
            Intent intent = new Intent(this, PermissionActivity.class);
            startActivity(intent);
        });
    }
}