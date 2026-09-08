package online.garcarzp.braindump.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.view.View
import android.widget.RemoteViews
import online.garcarzp.braindump.MainActivity
import online.garcarzp.braindump.R

class BrainDumpWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        for (appWidgetId in appWidgetIds) {
            updateAppWidget(context, appWidgetManager, appWidgetId)
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action == ACTION_REFRESH_WIDGET) {
            WidgetUpdateWorker.enqueueImmediate(context)
        }
    }

    override fun onEnabled(context: Context) {
        super.onEnabled(context)
        // Schedule periodic sync via WorkManager
        WidgetUpdateWorker.enqueuePeriodic(context)
        // Perform immediate fetch on widget placement
        WidgetUpdateWorker.enqueueImmediate(context)
    }

    companion object {
        const val ACTION_REFRESH_WIDGET = "online.garcarzp.braindump.ACTION_REFRESH_WIDGET"

        fun updateAppWidget(
            context: Context,
            appWidgetManager: AppWidgetManager,
            appWidgetId: Int
        ) {
            val views = RemoteViews(context.packageName, R.layout.widget_braindump_4x2)
            val prefs = WidgetPreferences(context)
            val tasks = prefs.getCachedTasks()
            val totalOpen = prefs.totalOpen

            // 1. Header Count Badge
            views.setTextViewText(R.id.widget_count_badge, totalOpen.toString())

            // 2. Configure empty view for ListView
            views.setEmptyView(R.id.widget_task_list, R.id.widget_empty_view)

            // 3. PendingIntent: Click on Header / Logo -> opens MainActivity
            val mainIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            }
            val mainPendingIntent = PendingIntent.getActivity(
                context,
                0,
                mainIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            views.setOnClickPendingIntent(R.id.widget_header_left, mainPendingIntent)

            // 4. PendingIntent: Click on '+' Add Task button -> opens MainActivity in manual add mode (?action=add)
            val addIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra(MainActivity.EXTRA_ACTION, MainActivity.ACTION_ADD)
            }
            val addPendingIntent = PendingIntent.getActivity(
                context,
                1,
                addIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            views.setOnClickPendingIntent(R.id.btn_widget_add, addPendingIntent)

            // 5. PendingIntent: Click on '🎤' Mic button -> opens MainActivity in voice record mode (?action=record)
            val recordIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra(MainActivity.EXTRA_ACTION, MainActivity.ACTION_RECORD)
            }
            val recordPendingIntent = PendingIntent.getActivity(
                context,
                2,
                recordIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            views.setOnClickPendingIntent(R.id.btn_widget_mic, recordPendingIntent)

            // 6. PendingIntent: Click on '🔄' Refresh button -> triggers immediate background sync
            val refreshIntent = Intent(context, BrainDumpWidgetProvider::class.java).apply {
                action = ACTION_REFRESH_WIDGET
            }
            val refreshPendingIntent = PendingIntent.getBroadcast(
                context,
                3,
                refreshIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            views.setOnClickPendingIntent(R.id.btn_widget_refresh, refreshPendingIntent)

            // 7. Bind ListView Adapter via TaskWidgetService
            val serviceIntent = Intent(context, TaskWidgetService::class.java).apply {
                putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
                data = Uri.parse(toUri(Intent.URI_INTENT_SCHEME))
            }
            views.setRemoteAdapter(R.id.widget_task_list, serviceIntent)

            // 8. Template PendingIntent for ListView items
            val itemClickIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            }
            val itemClickPendingIntent = PendingIntent.getActivity(
                context,
                4,
                itemClickIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            views.setPendingIntentTemplate(R.id.widget_task_list, itemClickPendingIntent)

            // Apply updates to widget
            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
    }
}
