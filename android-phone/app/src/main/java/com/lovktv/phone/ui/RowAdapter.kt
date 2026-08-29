package com.lovktv.phone.ui

import com.lovktv.phone.R

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.Button
import android.widget.TextView

class RowAdapter(
    private val inflater: LayoutInflater,
    private val onAction: (Row, String) -> Unit,
) : BaseAdapter() {
    data class Row(
        val key: String,
        val title: String,
        val meta: String,
        val action: String,
        val action2: String = "",
        val enabled: Boolean = true,
        val payload: Any? = null,
    )

    private val items = mutableListOf<Row>()

    fun replace(rows: List<Row>) {
        items.clear()
        items.addAll(rows)
        notifyDataSetChanged()
    }

    override fun getCount(): Int = items.size

    override fun getItem(position: Int): Row = items[position]

    override fun getItemId(position: Int): Long = items[position].key.hashCode().toLong()

    override fun getView(position: Int, convertView: View?, parent: ViewGroup?): View {
        val view = convertView ?: inflater.inflate(R.layout.item_row, parent, false)
        val row = items[position]
        view.findViewById<TextView>(R.id.title).text = row.title
        view.findViewById<TextView>(R.id.meta).text = row.meta
        val button = view.findViewById<Button>(R.id.action)
        button.text = row.action
        button.isEnabled = row.enabled
        button.setOnClickListener { onAction(row, row.action) }
        val extra = view.findViewById<Button>(R.id.action2)
        if (row.action2.isBlank()) {
            extra.visibility = View.GONE
        } else {
            extra.visibility = View.VISIBLE
            extra.text = row.action2
            extra.isEnabled = row.enabled
            extra.setOnClickListener { onAction(row, row.action2) }
        }
        return view
    }
}
