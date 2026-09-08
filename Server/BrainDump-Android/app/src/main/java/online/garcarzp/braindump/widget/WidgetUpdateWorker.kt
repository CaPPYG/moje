package online.garcarzp.braindump.widget

import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Context
import android.util.Log
import androidx.work.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import online.garcarzp.braindump.R
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class WidgetUpdateWorker(
    appContext: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(appContext, workerParams) {

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val prefs = WidgetPreferences(applicationContext)

        try {
            // Build URL with password parameter as fallback, and send X-Master-Password header
            val targetUrl = "${prefs.apiUrl}?password=${prefs.masterPassword}&limit=15"
            val request = Request.Builder()
                .url(targetUrl)
                .header("X-Master-Password", prefs.masterPassword)
                .header("Accept", "application/json")
                .get()
                .build()

            val response = httpClient.newCall(request).execute()
            if (!response.isSuccessful) {
                Log.w(TAG, "Widget API call failed with code: ${response.code}")
                return@withContext Result.retry()
            }

            val bodyString = response.body?.string() ?: return@withContext Result.failure()
            val json = JSONObject(bodyString)

            val totalOpen = json.optInt("total_open", 0)
            val tasksArray = json.optJSONArray("tasks")
            val taskList = mutableListOf<TaskWidgetItem>()

            if (tasksArray != null) {
                for (i in 0 until tasksArray.length()) {
                    val item = tasksArray.getJSONObject(i)
                    taskList.add(
                        TaskWidgetItem(
                            id = item.optInt("id", 0),
                            text = item.optString("text", ""),
                            category = item.optString("category", "Other")
                        )
                    )
                }
            }

            // Save to SharedPreferences
            prefs.saveTasks(totalOpen, taskList)

            // Notify Widget Manager to refresh UI & ListView data
            val appWidgetManager = AppWidgetManager.getInstance(applicationContext)
            val componentName = ComponentName(applicationContext, BrainDumpWidgetProvider::class.java)
            val appWidgetIds = appWidgetManager.getAppWidgetIds(componentName)

            // Trigger list view data reload
            appWidgetManager.notifyAppWidgetViewDataChanged(appWidgetIds, R.id.widget_task_list)

            // Re-render widget remote views (for total badge and empty view state)
            for (widgetId in appWidgetIds) {
                BrainDumpWidgetProvider.updateAppWidget(applicationContext, appWidgetManager, widgetId)
            }

            Log.i(TAG, "Widget updated successfully. Total open tasks: $totalOpen")
            Result.success()
        } catch (e: Exception) {
            Log.e(TAG, "Error updating widget from API: ${e.message}", e)
            Result.retry()
        }
    }

    companion object {
        private const val TAG = "WidgetUpdateWorker"
        private const val PERIODIC_WORK_TAG = "braindump_periodic_widget_sync"
        private const val IMMEDIATE_WORK_TAG = "braindump_immediate_widget_sync"

        fun enqueuePeriodic(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val periodicRequest = PeriodicWorkRequestBuilder<WidgetUpdateWorker>(
                15, TimeUnit.MINUTES,
                5, TimeUnit.MINUTES
            )
                .setConstraints(constraints)
                .addTag(PERIODIC_WORK_TAG)
                .build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                PERIODIC_WORK_TAG,
                ExistingPeriodicWorkPolicy.KEEP,
                periodicRequest
            )
        }

        fun enqueueImmediate(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val oneTimeRequest = OneTimeWorkRequestBuilder<WidgetUpdateWorker>()
                .setConstraints(constraints)
                .addTag(IMMEDIATE_WORK_TAG)
                .build()

            WorkManager.getInstance(context).enqueue(oneTimeRequest)
        }
    }
}
