package com.example.entangle;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.hardware.display.DisplayManager;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.Surface;
import android.view.WindowManager;
import androidx.core.app.NotificationCompat;
import java.io.IOException;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;

public class ScreenMirrorService extends Service {
    private static final String TAG = "ScreenMirror";
    private static final int PORT = 5555;
    private static final int VIDEO_BITRATE = 5000000; // 5 Mbps
    private static final int VIDEO_FPS = 30;

    private MediaProjection mediaProjection;
    private MediaCodec encoder;
    private Surface encoderSurface;
    private Thread serverThread;
    private Socket clientSocket;
    private boolean isRunning = true;
    private ServerSocket serverSocket;

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Log.d(TAG, "onStartCommand called");

        // Create notification for foreground service
        createNotificationChannel();
        Notification notification = createNotification();
        startForeground(1, notification);

        Log.d(TAG, "Foreground notification started");

        if (intent == null) {
            Log.e(TAG, "Intent is null!");
            return START_STICKY;
        }

        // Get MediaProjection from permission result
        int resultCode = intent.getIntExtra("resultCode", -1);
        Intent resultData = intent.getParcelableExtra("resultData");

        Log.d(TAG, "resultCode: " + resultCode);
        Log.d(TAG, "resultData: " + (resultData != null ? "OK" : "NULL"));

        if (resultCode == -1 && resultData != null) {
            Log.d(TAG, "Getting media projection");

            MediaProjectionManager projectionManager =
                    (MediaProjectionManager) getSystemService(MEDIA_PROJECTION_SERVICE);
            mediaProjection = projectionManager.getMediaProjection(resultCode, resultData);

            Log.d(TAG, "MediaProjection obtained: " + (mediaProjection != null ? "OK" : "NULL"));

            if (mediaProjection != null) {
                mediaProjection.registerCallback(new MediaProjection.Callback() {
                    @Override
                    public void onStop() {
                        Log.d(TAG, "MediaProjection stopped");
                        isRunning = false;
                    }
                }, new Handler(Looper.getMainLooper()));
            }

            // Start streaming in background thread
            serverThread = new Thread(this::startServer);
            serverThread.start();

            Log.d(TAG, "Server thread started");
        } else {
            Log.e(TAG, "Failed to get permission data");
        }

        return START_STICKY;
    }

    private void startServer() {
        int retries = 5;
        int retryDelay = 1000; // 1 second

        while (retries > 0 && isRunning) {
            try {
                serverSocket = new ServerSocket();
                serverSocket.setReuseAddress(true);
                serverSocket.bind(new java.net.InetSocketAddress(5555));

                Log.d(TAG, "Server listening on port 5555");

                while (isRunning && !serverSocket.isClosed()) {
                    try {
                        serverSocket.setSoTimeout(1000);
                        clientSocket = serverSocket.accept();
                        Log.d(TAG, "Client connected");
                        startScreenCapture();
                    } catch (java.net.SocketTimeoutException e) {
                        continue;
                    }
                }
                break; // Success, exit retry loop

            } catch (IOException e) {
                retries--;
                Log.e(TAG, "Server error (retries left: " + retries + ")", e);

                if (retries > 0) {
                    try {
                        Thread.sleep(retryDelay);
                        Log.d(TAG, "Retrying to bind port...");
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                    }
                }
            }
        }

        if (retries == 0) {
            Log.e(TAG, "Failed to bind port after retries");
        }
    }

    private void startScreenCapture() {
        try {
            // Get display metrics
            WindowManager windowManager = getSystemService(WindowManager.class);
            DisplayMetrics metrics = new DisplayMetrics();
            windowManager.getDefaultDisplay().getMetrics(metrics);

            int width = metrics.widthPixels;
            int height = metrics.heightPixels;
            int dpi = metrics.densityDpi;

            Log.d(TAG, "Screen size: " + width + "x" + height);

            // Create H.264 encoder
            setupEncoder(width, height);

            // Create virtual display that feeds into encoder
            mediaProjection.createVirtualDisplay(
                    "ScreenCapture",
                    width, height, dpi,
                    DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                    encoderSurface,
                    null, null
            );

            // Read encoded frames and send to client
            readAndSendEncodedFrames();

        } catch (Exception e) {
            Log.e(TAG, "Capture error", e);
        }
    }

    private void setupEncoder(int width, int height) throws IOException {
        MediaFormat format = MediaFormat.createVideoFormat("video/avc", width, height);

        format.setInteger(
                MediaFormat.KEY_COLOR_FORMAT,
                MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface
        );
        format.setInteger(MediaFormat.KEY_BIT_RATE, VIDEO_BITRATE);
        format.setInteger(MediaFormat.KEY_FRAME_RATE, VIDEO_FPS);
        format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1); // I-frame every 1 second

        encoder = MediaCodec.createEncoderByType("video/avc");
        encoder.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);

        encoderSurface = encoder.createInputSurface();
        encoder.start();

        Log.d(TAG, "Encoder created");
    }

    private void readAndSendEncodedFrames() {
        try {
            OutputStream out = clientSocket.getOutputStream();
            MediaCodec.BufferInfo bufferInfo = new MediaCodec.BufferInfo();

            while (isRunning && clientSocket.isConnected()) {
                // Get encoded frame from MediaCodec
                int outputIndex = encoder.dequeueOutputBuffer(bufferInfo, 10000);

                if (outputIndex >= 0) {
                    ByteBuffer encodedData = encoder.getOutputBuffer(outputIndex);

                    // Send frame with header (codec config / SPS+PPS included,
                    // required for the decoder to parse subsequent frames)
                    sendFrame(out, encodedData, bufferInfo);

                    encoder.releaseOutputBuffer(outputIndex, false);
                }
            }
        } catch (IOException e) {
            Log.e(TAG, "Send error", e);
        } finally {
            cleanup();
        }
    }

    private void sendFrame(OutputStream out, ByteBuffer data, MediaCodec.BufferInfo info)
            throws IOException {
        // Protocol: [codec_id(1)] [pts(8)] [size(4)] [data]
        byte[] header = new byte[13];

        // Codec ID: 0 = H.264
        header[0] = 0;

        // PTS (presentation timestamp)
        long pts = info.presentationTimeUs;
        header[1] = (byte) ((pts >> 56) & 0xFF);
        header[2] = (byte) ((pts >> 48) & 0xFF);
        header[3] = (byte) ((pts >> 40) & 0xFF);
        header[4] = (byte) ((pts >> 32) & 0xFF);
        header[5] = (byte) ((pts >> 24) & 0xFF);
        header[6] = (byte) ((pts >> 16) & 0xFF);
        header[7] = (byte) ((pts >> 8) & 0xFF);
        header[8] = (byte) (pts & 0xFF);

        // Frame size
        int size = data.remaining();
        header[9] = (byte) ((size >> 24) & 0xFF);
        header[10] = (byte) ((size >> 16) & 0xFF);
        header[11] = (byte) ((size >> 8) & 0xFF);
        header[12] = (byte) (size & 0xFF);

        // Send header + data
        out.write(header);
        byte[] frameBytes = new byte[size];
        data.get(frameBytes);
        out.write(frameBytes);
        out.flush();

        Log.d(TAG, "Sent frame: " + size + " bytes");
    }

    private void cleanup() {
        isRunning = false;

        // Close server socket first
        try {
            if (serverSocket != null && !serverSocket.isClosed()) {
                serverSocket.close();
                Log.d(TAG, "ServerSocket cleanup");
            }
        } catch (IOException e) {
            Log.e(TAG, "Error closing server socket in cleanup", e);
        }

        // Close encoder
        if (encoder != null) {
            try {
                encoder.stop();
                encoder.release();
            } catch (Exception e) {
                Log.e(TAG, "Encoder cleanup error", e);
            }
        }

        // Stop media projection
        if (mediaProjection != null) {
            mediaProjection.stop();
        }

        // Close client socket
        try {
            if (clientSocket != null && !clientSocket.isClosed()) {
                clientSocket.close();
            }
        } catch (IOException e) {
            Log.e(TAG, "Close error", e);
        }
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    "screenmirror",
                    "Screen Mirror",
                    NotificationManager.IMPORTANCE_LOW
            );
            NotificationManager manager = getSystemService(NotificationManager.class);
            manager.createNotificationChannel(channel);
        }
    }

    private Notification createNotification() {
        return new NotificationCompat.Builder(this, "screenmirror")
                .setContentTitle("Screen Mirroring")
                .setContentText("Streaming screen...")
                .build();
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        cleanup();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}